#include "ros2_subscriber_callbacks.hpp"
#include "utils/Logger.hpp"
#include <iostream>
#include "avvtn_capture/avvtn_capture.h"

void WakeUpResultCallback(const std_msgs::msg::String::SharedPtr msg)
{
    LOG_INFO("收到唤醒结果: {%s}", msg->data.c_str());
    if (msg->data == "success") {
        LOG_INFO("唤醒结果为 success");
        int ret = 0;

        if (AvvtnCapture::getInstance()) {
            // 设置波束为正前方beam为0
            ret = AvvtnCapture::getInstance()->test_set_beam("{\"params\":{\"beam\":\"0\"}}");
        } else {
            LOG_ERROR("g_avvtn_capture_instance is nullptr, cannot set beam");
        }
        if (ret == 0)
        {
            LOG_INFO("波束设置为正前方,beam_id=0");   
        } else {
            LOG_ERROR("Failed to set beam");
        }
    } else {
        LOG_WARN("唤醒结果不是 success, 不设置波束");
    }
}
