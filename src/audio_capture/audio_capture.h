/*
 * @Author: zwli24
 * @email: zwli24@iflytek.com
 * @Date: 2025-08-11 14:45:07
 * @LastEditTime: 2025-09-25 14:20:47
 * @Description: 音频捕获类
 */
#ifndef __AUDIO_CAPTURE_H__
#define __AUDIO_CAPTURE_H__

#include <memory>

#include "portaudio.h"
#include "thread"

/**
 * @brief 音频捕获类
 *
 * 该类封装了PortAudio库的功能，用于音频设备的捕获操作。
 * 支持音频设备的自动检测和重连功能。
 */
class AudioCapture
{
    /**
     * @brief 音频回调函数类型定义
     * @param handle 用户数据句柄
     * @param audio 音频数据指针
     * @param len 音频数据长度
     */
    using AudioCallback = void (*)(void *handle, const void *audio, int len);

public:
    /**
     * @brief 构造函数
     */
    AudioCapture();

    /**
     * @brief 析构函数
     */
    ~AudioCapture();

public:
    /**
     * @brief 开始音频捕获
     * @param handle 用户数据句柄，会传递给回调函数
     * @param cb 音频数据回调函数
     * @return 成功返回0，失败返回错误码
     */
    int Start(void *handle, AudioCallback cb);

    /**
     * @brief 停止音频捕获
     * @return 成功返回0，失败返回错误码
     */
    int Stop();

private:
    /**
     * @brief PortAudio流回调函数
     * @param input 输入音频数据
     * @param output 输出音频数据（未使用）
     * @param frameCount 帧数
     * @param timeInfo 时间信息
     * @param statusFlags 状态标志
     * @param userData 用户数据（AudioCapture实例指针）
     * @return 回调函数状态
     */
    static int paOutStreamBk(const void *input, void *output, unsigned long frameCount, const PaStreamCallbackTimeInfo *timeInfo, PaStreamCallbackFlags statusFlags, void *userData);

    /**
     * @brief 重新连接音频设备
     * @return 成功返回0，失败返回错误码
     */
    int Reconnect();

    /**
     * @brief 设备检测线程函数
     * 用于监控音频设备状态，在设备断开时自动重连
     */
    void DeviceCheckThread();

private:
    PaStream *stream_;                             ///< PortAudio流对象
    std::unique_ptr<short[]> data_filter_;         ///< 音频数据过滤器缓冲区
    std::unique_ptr<short[]> data_filter_mic8_;    ///< 8麦克风音频数据过滤器缓冲区

    void *handle_ = nullptr;    ///< 用户数据句柄
    AudioCallback cb_;          ///< 音频回调函数

    int device_index_;    ///< 音频设备索引
    bool is_running_;     ///< 运行状态标志

    std::thread device_check_thread_;                              ///< 设备检测线程
    std::chrono::high_resolution_clock::time_point start_time_;    ///< 开始时间点
};
#endif    // __AUDIO_CAPTURE_H__