#include "audio_capture.h"

#include <atomic>
#include <chrono>
#include <iostream>
#include <stdio.h>
#include <string.h>
#include <thread>

#include "utils/Logger.hpp"

AudioCapture::AudioCapture()
    : stream_(nullptr), data_filter_(new short[640 * 6]), data_filter_mic8_(new short[640 * 20]), is_running_(false), device_index_(-1)
{
}

AudioCapture::~AudioCapture()
{
    is_running_ = false;
    if (device_check_thread_.joinable())
    {
        device_check_thread_.join();
    }
}

int AudioCapture::paOutStreamBk(const void *input, void *output, unsigned long frameCount, const PaStreamCallbackTimeInfo *timeInfo, PaStreamCallbackFlags statusFlags, void *userData)
{
    AudioCapture *self    = (AudioCapture *)userData;
    const short *data_raw = (const short *)input;
    self->start_time_     = std::chrono::high_resolution_clock::now();

#if MIC_NUM == 4
    short *filter = self->data_filter_.get();
    for (int i = 0; i < frameCount; i++)
    {
        filter[i * 6]     = data_raw[i * 8 + 2];
        filter[i * 6 + 1] = data_raw[i * 8 + 3];
        filter[i * 6 + 2] = data_raw[i * 8 + 4];
        filter[i * 6 + 3] = data_raw[i * 8 + 5];
        filter[i * 6 + 4] = data_raw[i * 8 + 6];
        filter[i * 6 + 5] = data_raw[i * 8 + 7];
    }
    self->cb_(self->handle_, filter, frameCount * 2 * 6);
#elif MIC_NUM == 8
    short *filter = self->data_filter_mic8_.get();
    for (int i = 0; i < frameCount; i++)
    {
        filter[i * 20]      = data_raw[i * 12 + 0];
        filter[i * 20 + 1]  = data_raw[i * 12 + 1];
        filter[i * 20 + 2]  = data_raw[i * 12 + 2];
        filter[i * 20 + 3]  = data_raw[i * 12 + 3];
        filter[i * 20 + 4]  = data_raw[i * 12 + 4];
        filter[i * 20 + 5]  = data_raw[i * 12 + 5];
        filter[i * 20 + 6]  = data_raw[i * 12 + 6];
        filter[i * 20 + 7]  = data_raw[i * 12 + 7];
        filter[i * 20 + 8]  = data_raw[i * 12 + 8];
        filter[i * 20 + 9]  = data_raw[i * 12 + 9];
        filter[i * 20 + 10] = data_raw[i * 12 + 4];
        filter[i * 20 + 11] = data_raw[i * 12 + 5];
        filter[i * 20 + 12] = data_raw[i * 12 + 6];
        filter[i * 20 + 13] = data_raw[i * 12 + 7];
        filter[i * 20 + 14] = data_raw[i * 12 + 0];
        filter[i * 20 + 15] = data_raw[i * 12 + 1];
        filter[i * 20 + 16] = data_raw[i * 12 + 2];
        filter[i * 20 + 17] = data_raw[i * 12 + 3];
        filter[i * 20 + 18] = data_raw[i * 12 + 8];
        filter[i * 20 + 19] = data_raw[i * 12 + 9];
    }
    self->cb_(self->handle_, filter, frameCount * 2 * 20);
#else
    self->cb_(self->handle_, data_raw, frameCount * 2 * 8);
#endif
    return paContinue;
}

int AudioCapture::Start(void *handle, AudioCallback cb)
{
    handle_ = handle;
    cb_     = cb;

    if (is_running_)
    {
        std::cout << "AudioCapture is already running" << std::endl;
        LOG_ERROR("AudioCapture is already running");
        return -1;
    }

    is_running_          = true;
    device_check_thread_ = std::thread(&AudioCapture::DeviceCheckThread, this);
    start_time_          = std::chrono::high_resolution_clock::now();
    return Reconnect();
}

int AudioCapture::Reconnect()
{
    PaStreamParameters intputParameters;
    PaError err = paNoError;

    LOG_INFO("初始化 PortAudio");
    // 初始化 PortAudio
    err = Pa_Initialize();
    if (err != paNoError)
    {
        LOG_ERROR("PortAudio initialization failed: %s", Pa_GetErrorText(err));
        std::cout << "PortAudio initialization failed: " << Pa_GetErrorText(err) << std::endl;
        return -1;
    }

    LOG_INFO("查找MIC设备");
    // 查找设备
    int count     = Pa_GetDeviceCount();
    device_index_ = -1;
    for (int i = 0; i < count; ++i)
    {
        const PaDeviceInfo *info = Pa_GetDeviceInfo(i);
        if (strncmp(info->name, "AIUI-USB-MC", strlen("AIUI-USB-MC")) == 0)
        {
            device_index_ = i;
            std::cout << "Found USB mic at index = " << i << std::endl;
            LOG_INFO("Found USB mic at index = %d", i);
            break;
        }
    }

    if (device_index_ == -1)
    {
        std::cout << "Cannot find USB mic." << std::endl;
        LOG_ERROR("Cannot find USB mic.");
        return -1;
    }

    LOG_INFO("配置音频输入参数");
    // 配置输入参数
    const PaDeviceInfo *info                   = Pa_GetDeviceInfo(device_index_);
    intputParameters.device                    = device_index_;
    intputParameters.channelCount              = info->maxInputChannels;
    intputParameters.sampleFormat              = paInt16;
    intputParameters.suggestedLatency          = Pa_GetDeviceInfo(intputParameters.device)->defaultLowInputLatency;
    intputParameters.hostApiSpecificStreamInfo = nullptr;

    LOG_INFO("打开音频流");
    // 打开音频流
    err = Pa_OpenStream(&stream_, &intputParameters, nullptr, 16000, 640, paClipOff, paOutStreamBk, this);
    if (err != paNoError)
    {
        std::cout << "Failed to open audio stream: " << Pa_GetErrorText(err) << std::endl;
        LOG_ERROR("Failed to open audio stream: %s", Pa_GetErrorText(err));
        return -1;
    }

    LOG_INFO("启动音频流");
    // 启动音频流
    err = Pa_StartStream(stream_);
    if (err != paNoError)
    {
        std::cout << "Failed to start audio stream: " << Pa_GetErrorText(err) << std::endl;
        LOG_ERROR("Failed to start audio stream: %s", Pa_GetErrorText(err));
        return -1;
    }

    std::cout << "AudioCapture reconnected successfully" << std::endl;
    return 0;
}

int AudioCapture::Stop()
{
    PaError err = paNoError;
    if (stream_ != nullptr)
    {
        err = Pa_StopStream(stream_);
        if (err != paNoError)
        {
            std::cout << "PortAudio stream stopping failed: " << Pa_GetErrorText(err) << std::endl;
            LOG_ERROR("PortAudio stream stopping failed: %s", Pa_GetErrorText(err));
        }

        err = Pa_CloseStream(stream_);
        if (err != paNoError)
        {
            std::cout << "PortAudio stream closing failed: " << Pa_GetErrorText(err) << std::endl;
            LOG_ERROR("PortAudio stream closing failed: %s", Pa_GetErrorText(err));
        }
    }

    // 终止 PortAudio
    err = Pa_Terminate();
    if (err != paNoError)
    {
        std::cout << "PortAudio termination failed: " << Pa_GetErrorText(err) << std::endl;
        LOG_ERROR("PortAudio termination failed: %s", Pa_GetErrorText(err));
    }
    stream_ = nullptr;

    std::cout << "AudioCapture stopped" << std::endl;
    LOG_INFO("AudioCapture stopped");
    return 0;
}

void AudioCapture::DeviceCheckThread()
{
    while (is_running_)
    {
        LOG_TRACE("定期检查音频捕获设备是否连接成功");
        std::this_thread::sleep_for(std::chrono::seconds(2));
        auto now                              = std::chrono::high_resolution_clock::now();
        std::chrono::duration<double> elapsed = now - start_time_;
        if (abs(elapsed.count() > 5))
        {
            Stop();
            Reconnect();
        }
    }
}