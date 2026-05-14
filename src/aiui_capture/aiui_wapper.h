/**
 * @file aiui_wapper.h
 * @brief AIUI SDK封装头文件
 * @details 提供AIUI SDK的C++封装接口，包括语音识别、语音合成、NLP等功能
 * @author AIUI Team
 * @date 2024
 */
#ifndef AIUI_WRAPPER_H
#define AIUI_WRAPPER_H

// 标准库头文件
#include <memory>    // 智能指针
#include <string>    // 字符串处理

// 平台相关头文件和宏定义
#ifdef WIN32
#include <windows.h>
#define _HAS_STD_BYTE 0
#define AIUI_SLEEP    Sleep    // Windows平台睡眠函数
#else
#include <unistd.h>
#define AIUI_SLEEP(x) usleep(x * 1000)    // Linux平台睡眠函数，参数为毫秒
#endif

#undef AIUI_LIB_COMPILING
#include "json/json.h"    // JSON处理库
#include <cstring>        // C字符串处理
#include <fstream>        // 文件流操作
#include <iostream>       // 输入输出流

// AIUI SDK相关头文件
#include "aiui/AIUI_V2.h"                // AIUI SDK主头文件
#include "aiui/PcmPlayer_C.h"            // PCM音频播放器
#include "utils/Base64Util.h"            // Base64编码工具
#include "utils/IatResultUtil.h"         // 语音识别结果处理工具
#include "utils/StreamNlpTtsHelper.h"    // 流式NLP TTS助手

#ifdef _WIN32
#include <IPHlpApi.h>
#pragma comment(lib, "IPHLPAPI.lib")
#else
#include <net/if.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <unistd.h>
#endif

// AIUI版本定义，默认为版本3
#ifndef AIUI_VER
#define AIUI_VER 3
#endif

// 是否使用语义后合成。当在AIUI平台应用配置页面打开"语音合成"开关时，需要打开该宏
#define USE_POST_SEMANTIC_TTS

// 使用AIUI命名空间
using namespace aiui_va;
using namespace aiui_v2;

/**
 * @brief AIUI回调函数包结构体
 * @details 封装用户数据和回调函数指针，用于AIUI事件回调
 */
typedef struct aiui_callback_pack_s
{
    void *user_data;                                              // 用户自定义数据指针
    void (*handler)(void *user_data, const IAIUIEvent &event);    // AIUI事件回调函数指针
} aiui_callback_pack_t;

/**
 * @brief AIUI初始化参数包结构体
 * @details 包含AIUI SDK初始化所需的配置路径
 */
typedef struct aiui_init_pack_s
{
    std::string cfg_path;    // AIUI配置文件路径
} aiui_init_pack_t;

/**
 * @brief AIUI初始化参数结构体
 * @details 包含初始化参数和回调函数包
 */
typedef struct aiui_init_param_s
{
    aiui_init_pack_t param;           // 初始化参数包
    aiui_callback_pack_t callback;    // 回调函数包
} aiui_init_param_t;

// 前向声明
class AiuiWrapper;

/**
 * @brief TTS助手监听器类
 * @details 用于处理流式NLP
 * TTS助手的回调事件，继承自StreamNlpTtsHelper::Listener
 */
class TtsHelperListener : public StreamNlpTtsHelper::Listener
{
public:
    TtsHelperListener(AiuiWrapper *aiui_wrapper_ptr) : aiui_wrapper_ptr_(aiui_wrapper_ptr) {}
    ~TtsHelperListener() = default;

    /**
     * @brief 文本回调函数
     * @param textSeg 输出的文本片段
     */
    void onText(const StreamNlpTtsHelper::OutTextSeg &textSeg) override;

    /**
     * @brief 完成回调函数
     * @param fullText 完整的文本内容
     */
    void onFinish(const std::string &fullText) override;

    /**
     * @brief TTS音频数据回调函数
     * @param bizParamJson 业务参数JSON
     * @param audio 音频数据指针
     * @param len 音频数据长度
     */
    void onTtsData(const Json::Value &bizParamJson, const char *audio, int len) override;

private:
    AiuiWrapper *aiui_wrapper_ptr_;
};

/**
 * @brief AIUI事件监听器类
 * @details 负责处理AIUI SDK的各种事件回调，继承自IAIUIListener
 */
class AIUIListener : public IAIUIListener
{
public:
    AIUIListener(AiuiWrapper *aiui_wrapper_ptr) : aiui_wrapper_ptr_(aiui_wrapper_ptr) {}    // 默认构造函数
    ~AIUIListener() = default;                                                              // 默认析构函数

    /**
     * @brief 初始化监听器
     * @param aiui_callback_pack AIUI回调函数包
     * @return 成功返回0，失败返回错误码
     */
    int Init(const aiui_callback_pack_t &aiui_callback_pack);

    /**
     * @brief 销毁监听器
     * @return 成功返回0，失败返回错误码
     */
    int Destory();

    /**
     * @brief AIUI事件回调函数
     * @param event AIUI事件对象
     */
    void onEvent(const IAIUIEvent &event) override;

    std::shared_ptr<StreamNlpTtsHelper> tts_helper_ptr_;    // TTS播放辅助类实例

private:
    AiuiWrapper *aiui_wrapper_ptr_;    // AIUIWrapper指针

    aiui_callback_pack_t aiui_callback_pack_;    // AIUI回调函数包
};

/**
 * @brief AIUI SDK封装类
 * @details 提供AIUI SDK的简化接口，包括语音识别、语音合成、NLP等功能
 */
class AiuiWrapper
{
public:
    AiuiWrapper()  = default;    // 默认构造函数
    ~AiuiWrapper() = default;    // 默认析构函数

    /**
     * @brief 初始化AIUI SDK
     * @param aiui_cfg_path AIUI配置文件路径，默认为nullptr
     * @return 成功返回0，失败返回错误码
     */
    int Init(const aiui_init_param_t &aiui_init_param);

    /**
     * @brief 销毁AIUI SDK
     * @return 成功返回0，失败返回错误码
     */
    int Destory();

    // 唤醒和状态控制相关函数
    /**
     * @brief 唤醒AIUI
     */
    void Wakeup();

    /**
     * @brief 重置唤醒状态
     */
    void ResetWakeup();

    /**
     * @brief 开始AIUI服务
     */
    void Start();

    /**
     * @brief 停止AIUI服务
     */
    void Stop();

    /**
     * @brief 重置AIUI状态
     */
    void ResetAIUI();

    // 文本和音频输入相关函数
    /**
     * @brief 写入文本数据
     * @param text 要写入的文本
     * @param needWakeup 是否需要唤醒，默认为true
     */
    void WriteText(const std::string &text, bool needWakeup = true);

    /**
     * @brief 从本地文件写入音频数据
     * @param repeat 是否重复播放，默认为false
     */
    void WriteAudioFromLocal(bool repeat = false);

    /**
     * @brief 写入音频数据
     * @param data 音频数据指针
     * @param len 音频数据长度
     * @param is_stop 是否为停止标志，默认为false
     */
    void WriteAudio(const char *data, const int len, bool is_stop = false);

    /**
     * @brief 开始录制音频
     */
    void StartRecordAudio();

    /**
     * @brief 停止录制音频
     */
    void StopRecordAudio();

    // TTS语音合成相关函数
    /**
     * @brief 开始TTS语音合成
     * @param text 要合成的文本
     * @param tag 标签，默认为空字符串
     */
    void StartTTS(const std::string &text, const std::string &tag = "");

    /**
     * @brief 开始HTS语音合成
     * @param text 要合成的文本
     * @param tag 标签，默认为空字符串
     */
    void StartHTS(const std::string &text, const std::string &tag = "");

    /**
     * @brief 开始URL TTS语音合成
     * @param text 要合成的文本
     */
    void StartTTSUrl(const std::string &text);

    // 语法和对话相关函数
    /**
     * @brief 构建ESR语法
     */
    void BuildEsrGrammar();

    /**
     * @brief 清理对话历史
     */
    void CleanDialogHistory();

    /**
     * @brief 同步Schema数据
     * @param type 同步数据类型，默认为AIUIConstant::SYNC_DATA_SCHEMA
     */
    void SyncSchemaData(int type = AIUIConstant::SYNC_DATA_SCHEMA);

#if AIUI_VER == 2 || AIUI_VER == 3
    // AIUI版本2和3特有的功能
    /**
     * @brief 同步V2 SeeSay数据
     */
    void SyncV2SeeSayData();

    /**
     * @brief 注册语音克隆资源
     * @param resPath 资源路径，默认为空字符串
     */
    void VoiceCloneReg(const std::string &resPath = "");

    /**
     * @brief 删除语音克隆资源
     */
    void VoiceCloneDelRes();

    /**
     * @brief 查询语音克隆资源
     */
    void VoiceCloneQueryRes();

    /**
     * @brief 开始语音克隆TTS
     * @param text 要合成的文本
     * @param tag 标签，默认为空字符串
     */
    void StartVoiceCloneTTS(const std::string &text, const std::string &tag = "");

    /**
     * @brief AIUI登录
     */
    void AIUILogin();
#endif

    /**
     * @brief 查询同步Schema状态
     */
    void QuerySyncSchemaStatus();

    /**
     * @brief 操作唤醒词
     * @param op 操作类型
     */
    void OperateWakeupWord(int op);

    /**
     * @brief 获取MAC地址
     * @return MAC地址
     */
    std::string GetMacAddress();

    std::shared_ptr<AIUIListener> listener_;    // AIUI监听器智能指针

private:
    /**
     * @brief 初始化设置
     */
    void initSetting();

    /**
     * @brief 发送AIUI消息
     * @param cmd 命令类型
     * @param arg1 参数1，默认为0
     * @param arg2 参数2，默认为0
     * @param params 参数字符串，默认为空字符串
     * @param data AIUI缓冲区指针，默认为nullptr
     */
    void sendAIUIMessage(int cmd, int arg1 = 0, int arg2 = 0, const char *params = "", AIUIBuffer data = nullptr);


private:
    aiui_init_param_t aiui_init_param_;      // AIUI初始化参数
    IAIUIAgent *aiui_agent_;                 // AIUI代理对象指针
    std::string sync_session_id_;            // 同步会话ID
    std::string voice_clone_resource_id_;    // 语音克隆资源ID
    int pcm_player_index_;                   // PCM播放器索引
};

#endif