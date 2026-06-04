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
    S6_RESULT_FAIL    = "S6"   # 验证码验证失败
    S7_GENERAL_FAIL   = "S7"   # 通用失败（无法细分的错误）

# 通用业务流程节点（可扩展所有业务）
class BusinessFlowNode(Node):
    def __init__(self):
        super().__init__("business_flow_node")
        self.current_state = BusinessState.S0_IDLE

        # 发布
        self.pub_ui = self.create_publisher(String, "/page_switch_topic", 10)
        self.pub_tts = self.create_publisher(String, "/doubao_tts", 10)
        self.pub_state = self.create_publisher(String, "/current_state", 10)
        self.pub_api = self.create_publisher(String, "/api_request", 10)

        # 订阅
        self.create_subscription(String, "/touch_topic", self.on_touch_topic, 10)
        self.create_subscription(String, "/api_response", self.on_api_response, 10)

        # 语音业务缓存数据
        self.phone_number = ""
        self.sms_verify_code = ""
        
        # 话费查询结果缓存
        self.balance = 0
        self.account_expire_date = ""

        # 定时器引用（避免资源泄漏）
        self._state_timer = None

        self.get_logger().info("✅ 终端业务流程节点已启动")
        self.switch_state(BusinessState.S0_IDLE)

    def switch_state(self, new_state):
        """通用状态切换（所有业务共用逻辑）"""
        old_state = self.current_state
        
        # 如果状态没有改变，不执行任何操作（避免重复发布）
        if old_state == new_state:
            return
        
        self.current_state = new_state

        # 销毁旧定时器（避免资源泄漏）
        if self._state_timer is not None:
            self._state_timer.cancel()
            self._state_timer = None

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
            tts_text = ""

        elif s == BusinessState.S1_INPUT_PHONE:
            ui_page = "phone_input"
            tts_text = "请使用触屏输入11位手机号码"

        elif s == BusinessState.S2_WAIT_CODE:
            ui_page = "smscode_input"
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
            # 构建 detail 字段
            detail = json.dumps({
                "phone_number": self.phone_number,
                "balance": self.balance,
                "account_expire_date": self.account_expire_date
            }, ensure_ascii=False)

        elif s == BusinessState.S6_RESULT_FAIL:
            ui_page = "smscode_input"
            tts_text = "验证失败，请重新输入验证码"

        elif s == BusinessState.S7_GENERAL_FAIL:
            ui_page = "error"
            tts_text = "抱歉，系统暂时遇到问题，即将退出，请稍后重试"
            # 5秒后自动返回首页
            self._state_timer = self.create_timer(5.0, lambda: self.switch_state(BusinessState.S0_IDLE))

        # 执行
        if s == BusinessState.S5_RESULT_SUCCESS:
            # S5 状态需要发布 detail 字段
            ui_data = json.dumps({"page": ui_page, "detail": detail})
        else:
            ui_data = json.dumps({"page": ui_page})
        self.pub_ui.publish(String(data=ui_data))
        # 只在有文本时才发布 TTS，避免重复播报
        if tts_text:
            self.pub_tts.publish(String(data=tts_text))

    def on_touch_topic(self, msg):
        """语音业务指令处理（/touch_topic）"""
        try:
            data = json.loads(msg.data)
            business_type = data.get("business_type", "")
            content = data.get("content", "")

            self.get_logger().info(f"语音业务: business_type={business_type}, content={content}")

            if business_type == "query_balance":
                # 查询余额，需要当前在 S0 状态
                if self.current_state == BusinessState.S0_IDLE:
                    self.switch_state(BusinessState.S1_INPUT_PHONE)
                else:
                    # 不在首页，提示用户
                    self.get_logger().warning(f"当前状态 {self.current_state} 无法办理新业务")
                    self.pub_tts.publish(String(data="请先办理完当前业务或者退出哦"))

            elif business_type == "phone_number":
                # 收到手机号，校验格式
                if content and self.current_state == BusinessState.S1_INPUT_PHONE:
                    if self._validate_phone_number(content):
                        self.phone_number = content
                        self.get_logger().info(f"手机号校验通过: {content}")
                        # 发布请求发送验证码
                        self.pub_api.publish(String(data=json.dumps({
                            "func_name": "send_verify_code",
                            "params_json": json.dumps({"phone_number": content})
                        })))
                        self.switch_state(BusinessState.S2_WAIT_CODE)
                    else:
                        self.get_logger().error(f"手机号格式错误: {content}")
                        self.pub_tts.publish(String(data="手机号格式不正确，请重新输入"))
                        # 保持在 S1 状态，等待重新输入

            elif business_type == "sms_verify_code":
                # 收到验证码，发布到后端校验
                if content and self.current_state == BusinessState.S3_INPUT_CODE:
                    self.sms_verify_code = content
                    self.get_logger().info(f"收到验证码，开始校验: {content}")
                    # 发布验证码校验请求
                    self.pub_api.publish(String(data=json.dumps({
                        "func_name": "verify_code_check",
                        "params_json": json.dumps({
                            "phone_number": self.phone_number,
                            "verify_code": content
                        })
                    })))
                    self.switch_state(BusinessState.S4_VERIFYING)

            # 返回首页（统一播放提示音，只有不在 S0 时才切换状态）
            elif business_type == "back_home":
                # 统一播放提示音
                self.pub_tts.publish(String(data="好的，有需要再来找我哦"))
                # 只有不在 S0 状态时才切换
                if self.current_state != BusinessState.S0_IDLE:
                    self.switch_state(BusinessState.S0_IDLE)

        except json.JSONDecodeError as e:
            self.get_logger().error(f"/touch_topic JSON 解析失败: {e}")
        except Exception as e:
            self.get_logger().error(f"/touch_topic 处理异常: {e}")

    def _validate_phone_number(self, phone: str) -> bool:
        """校验手机号格式：11位，1开头，第二位3-9"""
        if len(phone) != 11:
            return False
        if not phone.startswith('1'):
            return False
        if phone[1] not in '3456789':
            return False
        if not phone.isdigit():
            return False
        return True

    def on_api_response(self, msg):
        """统一接收 API 调用返回结果"""
        try:
            data = json.loads(msg.data)
            func_name = data.get("func_name", "")
            code = data.get("code", -1)
            message = data.get("message", "")
            data_json_str = data.get("data_json", "{}")

            # 解析 data_json
            try:
                data_json = json.loads(data_json_str)
            except json.JSONDecodeError:
                data_json = {}

            self.get_logger().info(f"API 响应: func_name={func_name}, code={code}, message={message}")

            # 根据 func_name 分发到不同的处理函数
            if func_name == "send_verify_code":
                self._handle_send_verify_code_result(code, message, data_json)
            elif func_name == "verify_code_check":
                self._handle_verify_code_result(code, message, data_json)
            elif func_name == "query_balance":
                self._handle_query_balance_result(code, message, data_json)
            else:
                self.get_logger().warning(f"未知的 func_name: {func_name}")

        except json.JSONDecodeError as e:
            self.get_logger().error(f"/api_response JSON 解析失败: {e}")
        except Exception as e:
            self.get_logger().error(f"/api_response 处理异常: {e}")

    def _handle_send_verify_code_result(self, code, message, data_json):
        """处理发送验证码结果"""
        if code == 0:
            self.get_logger().info(f"验证码发送成功: {message}")
            self.switch_state(BusinessState.S3_INPUT_CODE)
        else:
            self.get_logger().error(f"验证码发送失败: {message}")
            self.pub_tts.publish(String(data="验证码发送失败"))
            self.switch_state(BusinessState.S7_GENERAL_FAIL)
            # 保存定时器引用，下次切换状态时会自动销毁
            self._state_timer = self.create_timer(2.0, lambda: self.switch_state(BusinessState.S1_INPUT_PHONE))

    def _handle_verify_code_result(self, code, message, data_json):
        """处理验证码校验结果"""
        if code == 0:
            self.get_logger().info(f"验证码校验成功: {message}")
            # 验证码校验成功后，先不跳转状态，而是发送查询话费请求
            self.get_logger().info(f"发送话费查询请求，手机号: {self.phone_number}")
            self.pub_api.publish(String(data=json.dumps({
                "func_name": "query_balance",
                "params_json": json.dumps({"phone_number": self.phone_number})
            })))
            # 保持当前状态 S3，等待后端返回查询结果后再跳转
        else:
            self.get_logger().error(f"验证码校验失败: {message}")
            self.pub_tts.publish(String(data="验证码校验失败"))
            self.switch_state(BusinessState.S6_RESULT_FAIL)
            self._state_timer = self.create_timer(2.0, lambda: self.switch_state(BusinessState.S3_INPUT_CODE))

    def _handle_query_balance_result(self, code, message, data_json):
        """处理话费查询结果"""
        if code == 0:
            self.balance = data_json.get("balance", 0)
            self.account_expire_date = data_json.get("account_expire_date", "")
            self.get_logger().info(f"话费查询成功: 余额 {self.balance} 元，账户有效期 {self.account_expire_date}")
            self.switch_state(BusinessState.S5_RESULT_SUCCESS)
        else:
            self.get_logger().error(f"话费查询失败: {message}")
            self.pub_tts.publish(String(data="话费查询失败"))
            self.switch_state(BusinessState.S6_RESULT_FAIL)
            self._state_timer = self.create_timer(2.0, lambda: self.switch_state(BusinessState.S0_IDLE))

def main(args=None):
    rclpy.init(args=args)
    node = BusinessFlowNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
