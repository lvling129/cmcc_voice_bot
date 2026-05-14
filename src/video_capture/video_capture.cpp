#include "video_capture.h"

#include <chrono>
#include <iostream>
#include <libudev.h>
#include <pthread.h>    // 添加pthread头文件用于线程命名
#include <sys/syscall.h>
#include <sys/unistd.h>
#define VENDOR_ID  "0bda"
#define PRODUCT_ID "5161"

using namespace std;
VideoCapture::VideoCapture() : start_(false), index_(-1) {}

VideoCapture::~VideoCapture() {}

int VideoCapture::Start(void *handle, VideoCallback cb)
{
    handle_ = handle;
    cb_     = cb;
    index_  = get_camera_index();
    cout << "打开摄像头！" << endl;
    cap_.open(index_, cv::CAP_V4L2);
    if (!cap_.isOpened())    // 判断摄像头是否成功打开
    {
        cout << "无法打开摄像头！" << endl;
        return -1;
    }
    else
    {
        cout << "摄像头已成功打开。" << endl;
    }
    cap_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
    cap_.set(cv::CAP_PROP_FRAME_WIDTH, WIDTH);
    cap_.set(cv::CAP_PROP_FRAME_HEIGHT, HEIGHT);
    cap_.set(cv::CAP_PROP_FPS, 30);

    int frame_width  = static_cast<int>(cap_.get(cv::CAP_PROP_FRAME_WIDTH));
    int frame_height = static_cast<int>(cap_.get(cv::CAP_PROP_FRAME_HEIGHT));

    std::cout << "Current camera resolution: " << frame_width << "x" << frame_height << std::endl;
    start_     = true;
    double fps = cap_.get(cv::CAP_PROP_FPS);

    cap_thread_ = thread(&VideoCapture::CaptureFunc, this);
    return 0;
}

int VideoCapture::Stop()
{
    start_ = false;
    if (cap_thread_.joinable()) cap_thread_.join();
    if (cap_.isOpened()) cap_.release();
    std::cout << "VideoCapture stop" << std::endl;
    return 0;
}

void VideoCapture::CaptureFunc()
{
    // 设置线程名字
    pthread_setname_np(pthread_self(), "VideoCapture");

    cv::Mat frame;
    while (start_)
    {
        cap_ >> frame;
        if (frame.empty())
        {
            cout << "获取图像失败" << endl;
            cv::waitKey(1000);
            cap_.release();
            index_ = get_camera_index();
            cap_.open(index_, cv::CAP_V4L2);
            cap_.set(cv::CAP_PROP_FOURCC, cv::VideoWriter::fourcc('M', 'J', 'P', 'G'));
            cap_.set(cv::CAP_PROP_FRAME_WIDTH, WIDTH);
            cap_.set(cv::CAP_PROP_FRAME_HEIGHT, HEIGHT);
            cap_.set(cv::CAP_PROP_FPS, 30);
            continue;
        }
        cb_(handle_, frame.data, frame.cols, frame.rows);
    }
}

int VideoCapture::get_camera_index()
{
    struct udev *udev;
    struct udev_enumerate *enumerate;
    struct udev_list_entry *devices, *dev_list_entry;

    udev = udev_new();
    if (!udev)
    {
        std::cerr << "Failed to initialize udev" << std::endl;
        return -1;
    }

    enumerate = udev_enumerate_new(udev);
    udev_enumerate_add_match_subsystem(enumerate, "video4linux");
    udev_enumerate_scan_devices(enumerate);
    devices = udev_enumerate_get_list_entry(enumerate);

    udev_list_entry_foreach(dev_list_entry, devices)
    {
        const char *path;
        struct udev_device *dev;

        path = udev_list_entry_get_name(dev_list_entry);
        dev  = udev_device_new_from_syspath(udev, path);

        const char *vendorId  = udev_device_get_property_value(dev, "ID_VENDOR_ID");
        const char *productId = udev_device_get_property_value(dev, "ID_MODEL_ID");
        if (vendorId && productId && std::string(vendorId) == VENDOR_ID && std::string(productId) == PRODUCT_ID)
        {
            const char *devnode = udev_device_get_devnode(dev);
            std::cout << "Device path: " << devnode << std::endl;
            if (sscanf(devnode, "/dev/video%d", &index_) == 1)
            {
                std::cout << "Device index: " << index_ << std::endl;
            }
            udev_device_unref(dev);
            break;
        }

        udev_device_unref(dev);
    }

    udev_enumerate_unref(enumerate);
    udev_unref(udev);
    return index_;
}