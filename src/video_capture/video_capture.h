/*
 * @Author: zwli24
 * @Date: 2024-05-15 14:22:53
 * @Description: 视频捕获类头文件 - 用于摄像头视频流的捕获和处理
 */
#ifndef __VIDEO_CAPTURE_H__
#define __VIDEO_CAPTURE_H__

#include <opencv2/opencv.hpp>
#include <thread>


static const int WIDTH  = 1920;
static const int HEIGHT = 1080;

/**
 * @brief 视频捕获类
 *
 * 该类封装了OpenCV的视频捕获功能，支持：
 * - 自动检测指定厂商ID和产品ID的摄像头设备
 * - 多线程视频捕获，避免阻塞主线程
 * - 回调函数机制，实时处理捕获的视频帧
 * - 支持1920x1080分辨率，30fps的视频捕获
 */
class VideoCapture
{
    /**
     * @brief 视频回调函数类型定义
     * @param handle 用户数据句柄
     * @param image 图像数据指针
     * @param width 图像宽度
     * @param height 图像高度
     */
    using VideoCallback = void (*)(void *handle, const void *image, int width, int height);

public:
    /**
     * @brief 构造函数
     * 初始化视频捕获对象
     */
    VideoCapture();

    /**
     * @brief 析构函数
     * 清理资源，停止视频捕获
     */
    ~VideoCapture();

    /**
     * @brief 开始视频捕获
     * @param handle 用户数据句柄，会传递给回调函数
     * @param cb 视频帧回调函数
     * @return 成功返回0，失败返回-1
     */
    int Start(void *handle, VideoCallback cb);

    /**
     * @brief 停止视频捕获
     * @return 成功返回0
     */
    int Stop();

private:
    /**
     * @brief 视频捕获线程函数
     * 在独立线程中持续捕获视频帧并调用回调函数
     */
    void CaptureFunc();

    /**
     * @brief 获取摄像头设备索引
     * 通过udev枚举视频设备，查找指定厂商ID和产品ID的摄像头
     * @return 摄像头设备索引，失败返回-1
     */
    int get_camera_index();

private:
    cv::VideoCapture cap_;      ///< OpenCV视频捕获对象
    std::thread cap_thread_;    ///< 视频捕获线程
    bool start_;                ///< 捕获状态标志
    int index_;                 ///< 摄像头设备索引

    void *handle_ = nullptr;    ///< 用户数据句柄
    VideoCallback cb_;          ///< 视频回调函数指针
};
#endif    // __VIDEO_CAPTURE_H__