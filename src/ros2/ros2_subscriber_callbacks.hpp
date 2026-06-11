#ifndef ROS2_SUBSCRIBER_CALLBACKS_HPP
#define ROS2_SUBSCRIBER_CALLBACKS_HPP

#include <std_msgs/msg/string.hpp>

/**
 * @file ros2_subscriber_callbacks.hpp
 * @brief ROS2 话题订阅回调函数声明
 *
 * 本文件集中定义所有订阅 ROS2 话题时的回调函数。
 * 在 main.cpp 或其它模块中通过 ROSManager::subscribeTopic(topic_name, CallbackName) 注册使用。
 */

/**
 * @brief 唤醒结果话题回调
 * @param msg 话题消息
 * @note 话题名: wake_up_turn_result
 */
void WakeUpResultCallback(const std_msgs::msg::String::SharedPtr msg);

/**
 * @brief 触摸唤醒话题回调
 * @param msg 话题消息
 * @note 话题名: /touch_wakeup
 */
void TouchWakeupCallback(const std_msgs::msg::String::SharedPtr msg);

/**
 * @brief 声纹降噪开关话题回调
 * @param msg 话题消息，JSON格式: {"status": true/false}
 * @note 话题名: /voiceprint/switcher
 *       status=true: 声纹降噪已开启，跳过PCM发送给豆包
 *       status=false: 声纹降噪已关闭，正常发送PCM给豆包
 */
void VoiceprintSwitcherCallback(const std_msgs::msg::String::SharedPtr msg);

// 在此处添加更多订阅回调的声明，例如：
// void onCommand(const std_msgs::msg::String::SharedPtr msg);
// void onConfigUpdate(const std_msgs::msg::String::SharedPtr msg);

#endif // ROS2_SUBSCRIBER_CALLBACKS_HPP
