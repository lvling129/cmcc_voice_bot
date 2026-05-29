import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# 通用业务状态（所有业务共用）
class BusinessState:
    S0_IDLE           = "S0"   # 待机首页
    S1_INPUT_PHONE    = "S1"   # 手机号输入页
    S2_WAIT_CODE      = "S2"   # 等待验证码
    S3_INPUT_CODE     = "S3"   # 验证码输入页
    S4_VERIFYING      = "S4"   # 验证中
    S5_RESULT_SUCCESS = "S5"   # 业务办理成功
    S6_RESULT_FAIL    = "S6"   # 业务办理失败

# 通用业务流程节点（可扩展所有业务）
class BusinessFlowNode(Node):
    def __init__(self):
        super().__init__("business_flow_node")
        self.current_state = BusinessState.S0_IDLE

        # 发布
        self.pub_ui = self.create_publisher(String, "/ui/switch_page", 10)
        self.pub_tts = self.create_publisher(String, "/doubao_tts", 10)
        self.pub_state = self.create_publisher(String, "/business/current_state", 10)

        # 订阅
        self.create_subscription(String, "/ui/touch_event", self.on_ui_touch, 10)
        self.create_subscription(String, "/api/verify_result", self.on_api_result, 10)
        self.create_subscription(String, "/touch_topic", self.on_touch_topic, 10)

        # 语音业务缓存数据
        self.phone_number = ""
        self.sms_verify_code = ""

        self.get_logger().info("✅ 终端业务流程节点已启动")
        self.switch_state(BusinessState.S0_IDLE)

    def switch_state(self, new_state):
        """通用状态切换（所有业务共用逻辑）"""
        old_state = self.current_state
        self.current_state = new_state

        # 发布状态
        self.pub_state.publish(String(data=new_state))
        self.get_logger().info(f"状态变更: {old_state} → {new_state}")

        # 自动播报 + 切页
        self.auto_ui_and_tts()

    def auto_ui_and_tts(self):
        """根据当前状态自动输出UI和语音（通用）"""
        s = self.current_state
        ui_page = "home"
        tts_text = ""

        if s == BusinessState.S0_IDLE:
            ui_page = "home"
            tts_text = "请选择您要办理的业务"

        elif s == BusinessState.S1_INPUT_PHONE:
            ui_page = "phone_input"
            tts_text = "请使用触屏输入11位手机号码"

        elif s == BusinessState.S2_WAIT_CODE:
            ui_page = "loading"
            tts_text = "正在请求验证码，请稍候"

        elif s == BusinessState.S3_INPUT_CODE:
            ui_page = "smscode_input"
            tts_text = "请使用触屏输入短信验证码"

        elif s == BusinessState.S4_VERIFYING:
            ui_page = "smscode_verifying"
            tts_text = "正在验证信息，请稍候"

        elif s == BusinessState.S5_RESULT_SUCCESS:
            ui_page = "balance_result"
            tts_text = "已为您查询话费余额，请看屏幕"

        elif s == BusinessState.S6_RESULT_FAIL:
            ui_page = "fail"
            tts_text = "验证失败，请重新输入验证码"

        # 执行
        self.pub_ui.publish(String(data=ui_page))
        self.pub_tts.publish(String(data=tts_text))

    def on_ui_touch(self, msg):
        """触屏事件（所有业务共用触发方式）"""
        event = msg.data
        curr = self.current_state
        self.get_logger().info(f"触屏事件: {event}")

        # 选择业务 → 进入手机号页
        if event in ["balance", "traffic", "package", "sim_card"] and curr == BusinessState.S0_IDLE:
            self.switch_state(BusinessState.S1_INPUT_PHONE)

        # 手机号确认
        elif event == "phone_confirm" and curr == BusinessState.S1_INPUT_PHONE:
            self.switch_state(BusinessState.S2_WAIT_CODE)
            self.create_timer(1.2, lambda: self.switch_state(BusinessState.S3_INPUT_CODE))

        # 验证码确认
        elif event == "code_confirm" and curr == BusinessState.S3_INPUT_CODE:
            self.switch_state(BusinessState.S4_VERIFYING)

        # 返回首页
        elif event == "back_home":
            self.switch_state(BusinessState.S0_IDLE)

    def on_api_result(self, msg):
        """API 验证结果通用处理"""
        res = msg.data
        if res == "success":
            self.switch_state(BusinessState.S5_RESULT_SUCCESS)
            self.create_timer(5.0, lambda: self.switch_state(BusinessState.S0_IDLE))
        else:
            self.switch_state(BusinessState.S6_RESULT_FAIL)
            self.create_timer(2.0, lambda: self.switch_state(BusinessState.S3_INPUT_CODE))

    def on_touch_topic(self, msg):
        """语音业务指令处理（/touch_topic）"""
        try:
            data = json.loads(msg.data)
            business_type = data.get("business_type", "")
            content = data.get("content", "")
            
            self.get_logger().info(f"语音业务: business_type={business_type}, content={content}")

            if business_type == "query_balance":
                # 查询余额，进入手机号输入页
                if self.current_state == BusinessState.S0_IDLE:
                    self.switch_state(BusinessState.S1_INPUT_PHONE)

            elif business_type == "phone_number":
                # 收到手机号，直接进入验证码输入页
                if content and self.current_state == BusinessState.S1_INPUT_PHONE:
                    self.phone_number = content
                    self.get_logger().info(f"收到手机号: {content}")
                    self.switch_state(BusinessState.S3_INPUT_CODE)

            elif business_type == "sms_verify_code":
                # 收到验证码，自动确认
                if content and self.current_state == BusinessState.S3_INPUT_CODE:
                    self.sms_verify_code = content
                    self.get_logger().info(f"收到验证码: {content}")
                    self.switch_state(BusinessState.S5_RESULT_SUCCESS)

        except json.JSONDecodeError as e:
            self.get_logger().error(f"/touch_topic JSON 解析失败: {e}")
        except Exception as e:
            self.get_logger().error(f"/touch_topic 处理异常: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = BusinessFlowNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
