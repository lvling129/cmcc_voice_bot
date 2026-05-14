#pragma once

#include <iostream>
#include <fstream>
#include <string>
#include <memory>
#include <mutex>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <vector>
#include <atomic>
#include <queue>
#include <thread>
#include <condition_variable>
#include <cstdio>

namespace Logger {

// 日志级别枚举
enum class LogLevel {
    LOG_TRACE = 0,
    LOG_DEBUG = 1,
    LOG_INFO = 2,
    LOG_WARN = 3,
    LOG_ERROR = 4,
    LOG_FATAL = 5,
    LOG_OFF = 6
};

// 日志级别转字符串
inline const char* LevelToString(LogLevel level) {
    switch (level) {
        case LogLevel::LOG_TRACE: return "TRACE";
        case LogLevel::LOG_DEBUG: return "DEBUG";
        case LogLevel::LOG_INFO:  return "INFO ";
        case LogLevel::LOG_WARN:  return "WARN ";
        case LogLevel::LOG_ERROR: return "ERROR";
        case LogLevel::LOG_FATAL: return "FATAL";
        default: return "UNKNOWN";
    }
}

// 日志级别颜色（控制台输出）
inline const char* LevelToColor(LogLevel level) {
    switch (level) {
        case LogLevel::LOG_TRACE: return "\033[37m";  // 白色
        case LogLevel::LOG_DEBUG: return "\033[36m";  // 青色
        case LogLevel::LOG_INFO:  return "\033[32m";  // 绿色
        case LogLevel::LOG_WARN:  return "\033[33m";  // 黄色
        case LogLevel::LOG_ERROR: return "\033[31m";  // 红色
        case LogLevel::LOG_FATAL: return "\033[35m";  // 紫色
        default: return "\033[0m";
    }
}

// 日志条目
struct LogEntry {
    std::chrono::system_clock::time_point timestamp;
    LogLevel level;
    std::string message;
    std::string file;
    int line;
    std::thread::id threadId;
    
    LogEntry(LogLevel lvl, const std::string& msg, 
             const std::string& srcFile = "", int srcLine = 0)
        : level(lvl), message(msg), file(srcFile), line(srcLine),
          threadId(std::this_thread::get_id()) {
        timestamp = std::chrono::system_clock::now();
    }
};

// 日志格式化器基类
class LogFormatter {
public:
    virtual ~LogFormatter() = default;
    virtual std::string Format(const LogEntry& entry) = 0;
};

// 默认日志格式化器
class DefaultFormatter : public LogFormatter {
public:
    std::string Format(const LogEntry& entry) override {
        auto time = std::chrono::system_clock::to_time_t(entry.timestamp);
        auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
            entry.timestamp.time_since_epoch()).count() % 1000;
        
        std::stringstream ss;
        ss << std::put_time(std::localtime(&time), "%Y-%m-%d %H:%M:%S")
           << "." << std::setfill('0') << std::setw(3) << ms
           << " [" << LevelToString(entry.level) << "]"
           << " [thread:" << entry.threadId << "]";
        
        if (!entry.file.empty()) {
            // 提取文件名（不含路径）
            size_t pos = entry.file.find_last_of("/\\");
            std::string filename = (pos != std::string::npos) ? 
                                  entry.file.substr(pos + 1) : entry.file;
            ss << " [" << filename << ":" << entry.line << "]";
        }
        
        ss << " " << entry.message;
        return ss.str();
    }
};

// 日志输出目标基类
class LogSink {
public:
    virtual ~LogSink() = default;
    virtual void Write(const LogEntry& entry, const std::string& formatted) = 0;
    virtual void Flush() = 0;
};

// 控制台输出
class ConsoleSink : public LogSink {
private:
    bool useColors_;
    std::mutex mutex_;

public:
    explicit ConsoleSink(bool useColors = true) : useColors_(useColors) {}

    void Write(const LogEntry& entry, const std::string& formatted) override {
        std::lock_guard<std::mutex> lock(mutex_);
        if (useColors_) {
            std::cout << LevelToColor(entry.level) << formatted 
                     << "\033[0m" << std::endl;
        } else {
            std::cout << formatted << std::endl;
        }
    }

    void Flush() override {
        std::cout.flush();
    }
};

// 文件输出
class FileSink : public LogSink {
private:
    std::ofstream file_;
    std::mutex mutex_;
    std::string filename_;
    size_t maxSize_;          // 最大文件大小（字节）
    int maxFiles_;           // 最大文件数量
    bool dailyRolling_;      // 是否按天滚动
    
    // 移除ANSI颜色代码的辅助函数

    std::string StripANSICodes(const std::string& input) {
        std::string result;
        bool inEscape = false;
        
        for (size_t i = 0; i < input.size(); ++i) {
            if (inEscape) {
                // 如果在ANSI转义序列中，继续直到找到'm'
                if (input[i] == 'm') {
                    inEscape = false;
                }
                continue;
            }
            
            // 检查是否开始ANSI转义序列
            if (input[i] == '\033' && i + 1 < input.size() && input[i+1] == '[') {
                inEscape = true;
                i++; // 跳过'['字符
                continue;
            }
            
            result.push_back(input[i]);
        }
        
        return result;
    }

public:
    FileSink(const std::string& filename, size_t maxSize = 10 * 1024 * 1024,
             int maxFiles = 5, bool dailyRolling = false)
        : filename_(filename), maxSize_(maxSize), 
          maxFiles_(maxFiles), dailyRolling_(dailyRolling) {
        OpenFile();
    }
    
    ~FileSink() {
        if (file_.is_open()) {
            file_.close();
        }
    }
    
    void Write(const LogEntry& entry, const std::string& formatted) override {
        std::lock_guard<std::mutex> lock(mutex_);
        
        // 检查是否需要滚动文件
        CheckRollover();
        
        if (file_.is_open()) {
            // 移除颜色代码后写入
            std::string clean_text = StripANSICodes(formatted);
            file_ << clean_text << std::endl;
        }
    }

    void Flush() override {
        if (file_.is_open()) {
            file_.flush();
        }
    }
    
private:
    void OpenFile() {
        file_.open(filename_, std::ios::app);
        if (!file_.is_open()) {
            std::cerr << "Failed to open log file: " << filename_ << std::endl;
        }
    }
    
    void CheckRollover() {
        if (!file_.is_open()) return;
        
        // 检查文件大小
        file_.seekp(0, std::ios::end);
        size_t currentSize = file_.tellp();
        
        bool shouldRoll = false;
        
        // 文件大小检查
        if (currentSize >= maxSize_) {
            shouldRoll = true;
        }
        
        // 按天滚动检查
        if (dailyRolling_) {
            static std::string lastDate;
            auto now = std::chrono::system_clock::now();
            auto time = std::chrono::system_clock::to_time_t(now);
            std::stringstream ss;
            ss << std::put_time(std::localtime(&time), "%Y-%m-%d");
            std::string currentDate = ss.str();
            
            if (lastDate.empty()) {
                lastDate = currentDate;
            } else if (lastDate != currentDate) {
                shouldRoll = true;
                lastDate = currentDate;
            }
        }
        
        if (shouldRoll) {
            RolloverFiles();
        }
    }
    
    void RolloverFiles() {
        file_.close();
        
        // 删除最旧的文件
        std::string oldFile = filename_ + "." + std::to_string(maxFiles_);
        std::remove(oldFile.c_str());
        
        // 重命名现有文件
        for (int i = maxFiles_ - 1; i >= 1; --i) {
            std::string oldName = filename_ + "." + std::to_string(i);
            std::string newName = filename_ + "." + std::to_string(i + 1);
            std::rename(oldName.c_str(), newName.c_str());
        }
        
        // 重命名当前文件
        std::rename(filename_.c_str(), (filename_ + ".1").c_str());
        
        // 重新打开新文件
        OpenFile();
    }
};

// 异步日志输出
class AsyncSink : public LogSink {
private:
    std::unique_ptr<LogSink> sink_;
    std::queue<std::pair<LogEntry, std::string>> queue_;
    std::mutex queueMutex_;
    std::condition_variable cv_;
    std::atomic<bool> running_;
    std::thread worker_;
    
public:
    explicit AsyncSink(std::unique_ptr<LogSink> sink)
        : sink_(std::move(sink)), running_(true) {
        worker_ = std::thread(&AsyncSink::ProcessQueue, this);
    }
    
    ~AsyncSink() {
        Stop();
    }
    
    void Write(const LogEntry& entry, const std::string& formatted) override {
        {
            std::lock_guard<std::mutex> lock(queueMutex_);
            queue_.emplace(entry, formatted);
        }
        cv_.notify_one();
    }
    
    void Flush() override {
        sink_->Flush();
    }
    
    void Stop() {
        running_ = false;
        cv_.notify_one();
        if (worker_.joinable()) {
            worker_.join();
        }
    }
    
private:
    void ProcessQueue() {
        while (running_ || !queue_.empty()) {
            std::unique_lock<std::mutex> lock(queueMutex_);
            cv_.wait(lock, [this] { 
                return !queue_.empty() || !running_; 
            });
            
            if (!queue_.empty()) {
                auto item = queue_.front();
                queue_.pop();
                lock.unlock();
                
                sink_->Write(item.first, item.second);
            }
        }
    }
};

// 主日志器类
class Logger {
private:
    // 静态成员声明（在头文件中只有声明，没有定义）
    static std::shared_ptr<Logger> instance_;
    static std::mutex instanceMutex_;
    
    LogLevel level_;
    std::vector<std::unique_ptr<LogSink>> sinks_;
    std::unique_ptr<LogFormatter> formatter_;
    std::mutex mutex_;
    bool asyncMode_;
    
    // 私有构造函数
    Logger();
    
public:
    // 删除拷贝构造函数和赋值运算符
    Logger(const Logger&) = delete;
    Logger& operator=(const Logger&) = delete;
    
    static Logger& GetInstance();
    
    // 设置日志级别
    void SetLevel(LogLevel level);
    
    LogLevel GetLevel() const;
    
    // 添加输出目标
    void AddSink(std::unique_ptr<LogSink> sink);
    
    // 设置异步模式
    void SetAsyncMode(bool enable);
    
    // 设置格式化器
    void SetFormatter(std::unique_ptr<LogFormatter> formatter);
    
    // 日志记录主函数
    void Log(LogLevel level, const std::string& message,
             const std::string& file = "", int line = 0);
    
    // 刷新所有输出
    void Flush();
};

// 简单格式化实现（C++11兼容版本）
namespace fmt {
    // 基础版本：无额外参数
    inline std::string format(const char* format) {
        return format ? std::string(format) : std::string();
    }
    
    // 模板版本：有一个或多个参数
    template<typename Arg, typename... Args>
    inline std::string format(const char* format, Arg arg, Args... args) {
        if (!format) return std::string();
        
        const size_t size = snprintf(nullptr, 0, format, arg, args...) + 1;
        if (size <= 1) return std::string();
        
        std::vector<char> buf(size);
        snprintf(buf.data(), size, format, arg, args...);
        return std::string(buf.data(), buf.data() + size - 1);
    }
    
    // std::string版本
    inline std::string format(const std::string& str) {
        return str;
    }
}

// 便捷宏定义
#define LOG_TRACE(...)  Logger::Logger::GetInstance().Log(Logger::LogLevel::LOG_TRACE, Logger::fmt::format(__VA_ARGS__), __FILE__, __LINE__)
#define LOG_DEBUG(...)  Logger::Logger::GetInstance().Log(Logger::LogLevel::LOG_DEBUG, Logger::fmt::format(__VA_ARGS__), __FILE__, __LINE__)
#define LOG_INFO(...)   Logger::Logger::GetInstance().Log(Logger::LogLevel::LOG_INFO,  Logger::fmt::format(__VA_ARGS__), __FILE__, __LINE__)
#define LOG_WARN(...)   Logger::Logger::GetInstance().Log(Logger::LogLevel::LOG_WARN,  Logger::fmt::format(__VA_ARGS__), __FILE__, __LINE__)
#define LOG_ERROR(...)  Logger::Logger::GetInstance().Log(Logger::LogLevel::LOG_ERROR, Logger::fmt::format(__VA_ARGS__), __FILE__, __LINE__)
#define LOG_FATAL(...)  Logger::Logger::GetInstance().Log(Logger::LogLevel::LOG_FATAL, Logger::fmt::format(__VA_ARGS__), __FILE__, __LINE__)

} // namespace Logger