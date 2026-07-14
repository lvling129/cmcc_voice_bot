import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# 通用业务状态（所有业务共用）
class BusinessState:
    S0_IDLE           = "S0"   # 待机首页
    S1_INPUT_PHONE    = "S1"   # 手机号输入页
    S3_INPUT_CODE     = "S3"   # 验证码输入页
    S4_VERIFYING      = "S4"   # 验证中
    S5_BALANCE_RESULT  = "S5"   # 话费查询结果页
    S6_RESULT_FAIL    = "S6"   # 验证码验证失败
    S7_GENERAL_FAIL   = "S7"   # 通用失败（无法细分的错误）
    S8_INPUT_MONTH    = "S8"   # 年月输入页（查套餐用）
    S9_PACKAGE_RESULT = "S9"   # 套餐查询结果页
    S10_CONFIRM_SWITCH = "S10" # 业务切换二次确认弹窗
    S11_TRAFFIC_RESULT = "S11" # 流量查询结果页
    S12_NEW_SIM_CARD   = "S12" # 直接跳转新办卡H5页面

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
        self.pub_sleep = self.create_publisher(String, "/avvtn_sleep", 10)

        # 订阅
        self.create_subscription(String, "/touch_topic", self.on_touch_topic, 10)
        self.create_subscription(String, "/voice_topic", self.on_touch_topic, 10)  # 语音输入，处理逻辑同 touch_topic
        self.create_subscription(String, "/api_response", self.on_api_response, 10)

        # 语音业务缓存数据
        self.phone_number = ""
        self.sms_verify_code = ""
        self.current_business = ""  # 当前业务类型：query_balance / query_package
        
        # 话费查询结果缓存
        self.balance = 0
        self.account_expire_date = ""

        # 套餐查询缓存
        self.billCycle = ""  # 用户输入的年月，如 "202606"
        self.package_info = {}  # 套餐查询结果

        # 流量查询缓存
        self.traffic_info = {}  # 流量查询结果

        # 手机号输入错误计数（连续输错3次以上提示用户）
        self.phone_error_count = 0
        # 验证码输入错误计数（连续输错3次以上提示用户）
        self.verify_code_error_count = 0
        # 待切换的业务类型（用于 S10 确认弹窗后执行）
        self.pending_business = ""
        # 弹窗前的状态（用于取消切换时恢复）
        self.previous_state = BusinessState.S0_IDLE

        # 定时器引用（避免资源泄漏）
        self._state_timer = None

        self.get_logger().info("✅ 终端业务流程节点已启动")
        self.switch_state(BusinessState.S0_IDLE)

    def switch_state(self, new_state):
        """通用状态切换（所有业务共用逻辑）"""
        old_state = self.current_state
        
        # 如果状态没有改变，不执行任何操作（避免重复发布），但 S0 除外（需要强制刷新）
        if old_state == new_state and new_state != BusinessState.S0_IDLE:
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
            tts_text = "请在触屏上输入11位手机号码"

        elif s == BusinessState.S3_INPUT_CODE:
            ui_page = "smscode_input"
            tts_text = "请在触屏上输入短信验证码"

        elif s == BusinessState.S4_VERIFYING:
            ui_page = "smscode_verifying"
            tts_text = "正在验证信息，请稍候"

        elif s == BusinessState.S5_BALANCE_RESULT:
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

        elif s == BusinessState.S8_INPUT_MONTH:
            ui_page = "month_input"
            tts_text = "请在触屏上选择要查询的年月"

        elif s == BusinessState.S9_PACKAGE_RESULT:
            ui_page = "package_result"
            tts_text = "已为您查询套餐信息，请看屏幕"
            detail = json.dumps({
                "phone_number": self.package_info.get("phone_number", ""),
                "billCycle": self.package_info.get("billCycle", ""),
                "data_json": self.package_info.get("data_json", [])
            }, ensure_ascii=False)

        elif s == BusinessState.S10_CONFIRM_SWITCH:
            ui_page = "confirm_switch"
            # 业务名称映射（用于 TTS 播报）
            business_name_map = {
                "query_balance": "查话费",
                "query_package": "查套餐",
                "query_traffic": "查流量",
                "new_sim_card": "新办卡"
            }
            current_name = business_name_map.get(self.current_business, "未知")
            tts_text = f"您当前正在{current_name}流程中，请问是放弃还是继续？"
            detail = tts_text

        elif s == BusinessState.S11_TRAFFIC_RESULT:
            ui_page = "traffic_result"
            tts_text = "已为您查询流量信息，请看屏幕"
            detail = json.dumps({
                "phone_number": self.phone_number,
                "billCycle": self.billCycle,
                "data_json": self.traffic_info.get("data_json", [])
            }, ensure_ascii=False)

        elif s == BusinessState.S12_NEW_SIM_CARD:
            ui_page = "new_sim_card"
            tts_text = "已为您打开新办卡页面，请看屏幕"

        # 执行
        if s in (BusinessState.S5_BALANCE_RESULT, BusinessState.S9_PACKAGE_RESULT, BusinessState.S10_CONFIRM_SWITCH, BusinessState.S11_TRAFFIC_RESULT):
            # S5/S9/S10 状态需要发布 detail 字段
            ui_data = json.dumps({"page": ui_page, "detail": detail})
        else:
            ui_data = json.dumps({"page": ui_page})
        self.pub_ui.publish(String(data=ui_data))
        # 只在有文本时才发布 TTS，避免重复播报
        if tts_text:
            self.pub_tts.publish(String(data=tts_text))

    def on_touch_topic(self, msg):
        """语音业务指令处理（/voice_topic）"""
        """触屏业务指令处理（/touch_topic）"""
        try:
            data = json.loads(msg.data)
            business_type = data.get("business_type", "")
            content = data.get("content", "")

            self.get_logger().info(f"语音业务: business_type={business_type}, content={content}")

            if business_type == "query_balance":
                # 查询余额，需要当前在 S0 或 S5 或 S9 或 S11 或 S12 状态
                if self.current_state in (BusinessState.S0_IDLE, BusinessState.S5_BALANCE_RESULT, BusinessState.S9_PACKAGE_RESULT, BusinessState.S11_TRAFFIC_RESULT, BusinessState.S12_NEW_SIM_CARD):
                    self.current_business = "query_balance"
                    self.switch_state(BusinessState.S1_INPUT_PHONE)
                elif self.current_business == "query_balance":
                    # 新业务与当前业务相同，不弹窗，TTS提示
                    self.get_logger().info("用户请求的业务与当前业务相同，不弹窗")
                    self.pub_tts.publish(String(data="您当前已经在查话费流程中"))
                elif self.current_state == BusinessState.S10_CONFIRM_SWITCH:
                    # 已在弹窗状态，更新待切换业务即可，不重复弹窗
                    self.pending_business = "query_balance"
                    self.get_logger().info("已在弹窗状态，更新待切换业务为 query_balance")
                else:
                    # 不在首页，弹出二次确认弹窗
                    self.pending_business = "query_balance"
                    self.previous_state = self.current_state  # 保存弹窗前状态
                    self.get_logger().warning(f"当前状态 {self.current_state} 无法直接办理新业务，弹出确认弹窗")
                    self.switch_state(BusinessState.S10_CONFIRM_SWITCH)

            elif business_type == "query_package":
                # 查询套餐，需要当前在 S0 或 S5 或 S9 或 S11 或 S12 状态
                if self.current_state in (BusinessState.S0_IDLE, BusinessState.S5_BALANCE_RESULT, BusinessState.S9_PACKAGE_RESULT, BusinessState.S11_TRAFFIC_RESULT, BusinessState.S12_NEW_SIM_CARD):
                    self.current_business = "query_package"
                    self.switch_state(BusinessState.S1_INPUT_PHONE)
                elif self.current_business == "query_package":
                    # 新业务与当前业务相同，不弹窗，TTS提示
                    self.get_logger().info("用户请求的业务与当前业务相同，不弹窗")
                    self.pub_tts.publish(String(data="您当前已经在查套餐流程中"))
                elif self.current_state == BusinessState.S10_CONFIRM_SWITCH:
                    # 已在弹窗状态，更新待切换业务即可，不重复弹窗
                    self.pending_business = "query_package"
                    self.get_logger().info("已在弹窗状态，更新待切换业务为 query_package")
                else:
                    # 不在首页，弹出二次确认弹窗
                    self.pending_business = "query_package"
                    self.previous_state = self.current_state  # 保存弹窗前状态
                    self.get_logger().warning(f"当前状态 {self.current_state} 无法直接办理新业务，弹出确认弹窗")
                    self.switch_state(BusinessState.S10_CONFIRM_SWITCH)

            elif business_type == "query_traffic":
                # 查询流量，需要当前在 S0/S5/S9/S11/S12 状态
                if self.current_state in (BusinessState.S0_IDLE, BusinessState.S5_BALANCE_RESULT, BusinessState.S9_PACKAGE_RESULT, BusinessState.S11_TRAFFIC_RESULT, BusinessState.S12_NEW_SIM_CARD):
                    self.current_business = "query_traffic"
                    self.switch_state(BusinessState.S1_INPUT_PHONE)
                elif self.current_business == "query_traffic":
                    self.get_logger().info("用户请求的业务与当前业务相同，不弹窗")
                    self.pub_tts.publish(String(data="您当前已经在查流量流程中"))
                elif self.current_state == BusinessState.S10_CONFIRM_SWITCH:
                    self.pending_business = "query_traffic"
                    self.get_logger().info("已在弹窗状态，更新待切换业务为 query_traffic")
                else:
                    self.pending_business = "query_traffic"
                    self.previous_state = self.current_state
                    self.get_logger().warning(f"当前状态 {self.current_state} 无法直接办理新业务，弹出确认弹窗")
                    self.switch_state(BusinessState.S10_CONFIRM_SWITCH)

            elif business_type == "new_sim_card":
                # 新办卡，直接跳转到新办卡页面（无需手机号/验证码）
                if self.current_state in (BusinessState.S0_IDLE, BusinessState.S5_BALANCE_RESULT, BusinessState.S9_PACKAGE_RESULT, BusinessState.S11_TRAFFIC_RESULT, BusinessState.S12_NEW_SIM_CARD):
                    self.current_business = "new_sim_card"
                    self.switch_state(BusinessState.S12_NEW_SIM_CARD)
                elif self.current_business == "new_sim_card":
                    # 新业务与当前业务相同，不弹窗，TTS提示
                    self.get_logger().info("用户请求的业务与当前业务相同，不弹窗")
                    self.pub_tts.publish(String(data="您当前已经在新办卡流程中"))
                elif self.current_state == BusinessState.S10_CONFIRM_SWITCH:
                    # 已在弹窗状态，更新待切换业务即可，不重复弹窗
                    self.pending_business = "new_sim_card"
                    self.get_logger().info("已在弹窗状态，更新待切换业务为 new_sim_card")
                else:
                    # 不在首页，弹出二次确认弹窗
                    self.pending_business = "new_sim_card"
                    self.previous_state = self.current_state  # 保存弹窗前状态
                    self.get_logger().warning(f"当前状态 {self.current_state} 无法直接办理新业务，弹出确认弹窗")
                    self.switch_state(BusinessState.S10_CONFIRM_SWITCH)

            elif business_type == "phone_number":
                # 收到手机号，校验格式
                if self.current_state == BusinessState.S1_INPUT_PHONE:
                    # 连续3次以上输错，播放提示音，但仍继续校验
                    if self.phone_error_count >= 3:
                        self.get_logger().warning(f"连续 {self.phone_error_count} 次输错手机号")
                        self.pub_tts.publish(String(data=f"你已经连续{self.phone_error_count}次输错手机号"))
                    # 1. 手机号为空
                    if not content:
                        self.phone_error_count += 1
                        self.get_logger().warning("手机号为空")
                        self.pub_tts.publish(String(data="请输入手机号码"))
                        # 保持在 S1 状态，等待重新输入
                    # 2. 手机号位数不对
                    elif not self._validate_phone_number(content):
                        self.phone_error_count += 1
                        self.get_logger().error(f"手机号格式错误: {content}")
                        self.pub_tts.publish(String(data="请输入正确的11位手机号码"))
                        # 保持在 S1 状态，等待重新输入
                    else:
                        # 校验通过，重置错误计数
                        self.phone_error_count = 0
                        self.phone_number = content
                        self.get_logger().info(f"手机号校验通过: {content}")
                        # 发布请求发送验证码（保持 S1，等 API 返回后再切到 S3，避免重复发布 smscode_input）
                        self.pub_api.publish(String(data=json.dumps({
                            "func_name": "send_verify_code",
                            "params_json": json.dumps({"phone_number": content})
                        })))

            elif business_type == "resend_verify_code":
                # 重新发送验证码，使用已缓存的手机号
                if self.current_state == BusinessState.S3_INPUT_CODE and self.phone_number:
                    self.get_logger().info(f"重新发送验证码，手机号: {self.phone_number}")
                    self.pub_api.publish(String(data=json.dumps({
                        "func_name": "send_verify_code",
                        "params_json": json.dumps({"phone_number": self.phone_number})
                    })))
                else:
                    self.get_logger().warning(f"无法重发验证码: 状态={self.current_state}, 手机号={self.phone_number}")

            elif business_type == "sms_verify_code":
                # 收到验证码，校验后发布到后端校验
                if self.current_state == BusinessState.S3_INPUT_CODE:
                    # 连续3次以上输错，播放提示音，但仍继续校验
                    if self.verify_code_error_count >= 3:
                        self.get_logger().warning(f"连续 {self.verify_code_error_count} 次输错验证码")
                        self.pub_tts.publish(String(data="验证码错误次数过多，请稍后再试"))
                    # 1. 验证码为空
                    if not content:
                        self.verify_code_error_count += 1
                        self.get_logger().warning("验证码为空")
                        self.pub_tts.publish(String(data="请输入验证码"))
                        # 保持在 S3 状态，等待重新输入
                    # 2. 验证码位数不对（应为6位）
                    elif len(content) != 6 or not content.isdigit():
                        self.verify_code_error_count += 1
                        self.get_logger().error(f"验证码格式错误: {content}")
                        self.pub_tts.publish(String(data="请输入6位验证码"))
                        # 保持在 S3 状态，等待重新输入
                    else:
                        # 校验通过，发布到后端校验
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

            elif business_type == "bill_cycle":
                # 收到年月输入（查套餐/查流量流程）
                if content and self.current_state == BusinessState.S8_INPUT_MONTH:
                    self.billCycle = content
                    if self.current_business == "query_traffic":
                        self.get_logger().info(f"收到查询年月: {content}，开始查询流量")
                        self.pub_api.publish(String(data=json.dumps({
                            "func_name": "query_traffic_by_package",
                            "params_json": json.dumps({
                                "phone_number": self.phone_number,
                                "billCycle": content
                            })
                        })))
                    else:
                        self.get_logger().info(f"收到查询年月: {content}，开始查询套餐")
                        self.pub_api.publish(String(data=json.dumps({
                            "func_name": "query_package",
                            "params_json": json.dumps({
                                "phone_number": self.phone_number,
                                "billCycle": content
                            })
                        })))
                    self.switch_state(BusinessState.S4_VERIFYING)

            # 业务切换确认弹窗的用户选择（触屏）
            elif business_type == "interrupt_choice":
                if self.current_state != BusinessState.S10_CONFIRM_SWITCH:
                    return
                choice = content  # "continue" 或 "quit"
                if choice == "quit":
                    self._do_quit_current()
                else:
                    self._do_continue_current()

            # 业务切换确认弹窗的用户选择（语音 - 继续）
            elif business_type == "continue_current":
                if self.current_state != BusinessState.S10_CONFIRM_SWITCH:
                    return
                self._do_continue_current()

            # 返回首页（统一播放提示音，只有不在 S0 时才切换状态）
            elif business_type == "back_home":
                # S10 弹窗确认状态下收到 back_home，视为用户选择放弃当前业务、切换到新业务
                if self.current_state == BusinessState.S10_CONFIRM_SWITCH:
                    self.get_logger().info("S10 弹窗收到 back_home，用户选择切换到新业务")
                    self._do_quit_current()
                    return
                # 统一播放提示音
                self.pub_tts.publish(String(data="有需要再来找我哦"))
                # 重置错误计数和待切换业务
                self.phone_error_count = 0
                self.verify_code_error_count = 0
                self.pending_business = ""
                self.switch_state(BusinessState.S0_IDLE)
                self.pub_sleep.publish(String(data="sleep"))

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

    def _do_continue_current(self):
        """用户选择继续当前业务，返回弹窗前的页面"""
        self.get_logger().info(f"用户选择继续当前业务，返回弹窗前状态: {self.previous_state}")
        self.pending_business = ""
        self.switch_state(self.previous_state)

    def _do_quit_current(self):
        """用户选择放弃当前业务，切换到新业务"""
        self.get_logger().info(f"用户确认切换到新业务: {self.pending_business}")
        # 重置错误计数
        self.phone_error_count = 0
        self.verify_code_error_count = 0
        # 切换到新业务
        self.current_business = self.pending_business
        self.pending_business = ""
        self.switch_state(BusinessState.S1_INPUT_PHONE)

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
            elif func_name == "query_package":
                self._handle_query_package_result(code, message, data_json)
            elif func_name == "query_traffic_by_package":
                self._handle_query_traffic_result(code, message, data_json)
            elif func_name == "script_active_query":
                self._handle_script_query_result(code, message, data_json)
            else:
                self.get_logger().warning(f"未知的 func_name: {func_name}")

        except json.JSONDecodeError as e:
            self.get_logger().error(f"/api_response JSON 解析失败: {e}")
        except Exception as e:
            self.get_logger().error(f"/api_response 处理异常: {e}")

    def _handle_send_verify_code_result(self, code, message, data_json):
        """处理发送验证码结果（首次发送或重发均走此逻辑）"""
        # 状态守卫：S1（首次发送）或 S3（重发）时均可处理
        if self.current_state not in (BusinessState.S1_INPUT_PHONE, BusinessState.S3_INPUT_CODE):
            self.get_logger().warning(f"收到 send_verify_code 响应但当前状态为 {self.current_state}，忽略")
            return
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
        # 状态守卫：只有在 S4（验证中）时才处理
        if self.current_state != BusinessState.S4_VERIFYING:
            self.get_logger().warning(f"收到 verify_code_check 响应但当前状态为 {self.current_state}，忽略")
            return
        if code == 0:
            self.get_logger().info(f"验证码校验成功: {message}")
            # 校验成功，重置错误计数
            self.verify_code_error_count = 0
            if self.current_business in ("query_package", "query_traffic"):
                # 查套餐/查流量流程：验证成功后进入年月输入页
                self.get_logger().info(f"{self.current_business} 流程，进入年月输入页")
                self.switch_state(BusinessState.S8_INPUT_MONTH)
            else:
                # 查话费流程：验证码校验成功后，发送查询话费请求
                self.get_logger().info(f"发送话费查询请求，手机号: {self.phone_number}")
                self.pub_api.publish(String(data=json.dumps({
                    "func_name": "query_balance",
                    "params_json": json.dumps({"phone_number": self.phone_number})
                })))
                # 保持当前状态，等待后端返回查询结果后再跳转
        else:
            self.get_logger().error(f"验证码校验失败: {message}")
            self.pub_tts.publish(String(data="验证码校验失败"))
            self.switch_state(BusinessState.S6_RESULT_FAIL)
            self._state_timer = self.create_timer(2.0, lambda: self.switch_state(BusinessState.S3_INPUT_CODE))

    def _handle_query_balance_result(self, code, message, data_json):
        """处理话费查询结果"""
        # 状态守卫：只有在 S4（验证中/查询中）时才处理
        if self.current_state != BusinessState.S4_VERIFYING:
            self.get_logger().warning(f"收到 query_balance 响应但当前状态为 {self.current_state}，忽略")
            return
        if code == 0:
            self.balance = data_json.get("balance", 0)
            self.account_expire_date = data_json.get("account_expire_date", "")
            self.get_logger().info(f"话费查询成功: 余额 {self.balance} 元，账户有效期 {self.account_expire_date}")
            self.switch_state(BusinessState.S5_BALANCE_RESULT)
            # 异步触发营销推荐查询
            self._trigger_script_query()
        else:
            self.get_logger().error(f"话费查询失败: {message}")
            self.pub_tts.publish(String(data="话费查询失败"))
            self.switch_state(BusinessState.S6_RESULT_FAIL)
            self._state_timer = self.create_timer(2.0, lambda: self.switch_state(BusinessState.S0_IDLE))

    def _handle_query_package_result(self, code, message, data_json):
        """处理套餐查询结果"""
        # 状态守卫：只有在 S4（验证中/查询中）时才处理
        if self.current_state != BusinessState.S4_VERIFYING:
            self.get_logger().warning(f"收到 query_package 响应但当前状态为 {self.current_state}，忽略")
            return
        if code == 0:
            self.package_info = {
                "phone_number": data_json.get("servnumber", ""),
                "billCycle": data_json.get("billCycle", ""),
                "data_json": data_json.get("resources", [])
            }
            self.get_logger().info(f"套餐查询成功: {self.package_info}")
            self.switch_state(BusinessState.S9_PACKAGE_RESULT)
            # 异步触发营销推荐查询
            self._trigger_script_query()
        else:
            self.get_logger().error(f"套餐查询失败: {message}")
            self.pub_tts.publish(String(data="套餐查询失败"))
            self.switch_state(BusinessState.S6_RESULT_FAIL)
            self._state_timer = self.create_timer(2.0, lambda: self.switch_state(BusinessState.S0_IDLE))

    def _handle_query_traffic_result(self, code, message, data_json):
        """处理流量查询结果"""
        # 状态守卫：只有在 S4（验证中/查询中）时才处理
        if self.current_state != BusinessState.S4_VERIFYING:
            self.get_logger().warning(f"收到 query_traffic 响应但当前状态为 {self.current_state}，忽略")
            return
        if code == 0:
            self.traffic_info = {
                "data_json": data_json.get("package_list", [])
            }
            self.get_logger().info(f"流量查询成功: {self.traffic_info}")
            self.switch_state(BusinessState.S11_TRAFFIC_RESULT)
            # 异步触发营销推荐查询
            self._trigger_script_query()
        else:
            self.get_logger().error(f"流量查询失败: {message}")
            self.pub_tts.publish(String(data="流量查询失败"))
            self.switch_state(BusinessState.S6_RESULT_FAIL)
            self._state_timer = self.create_timer(2.0, lambda: self.switch_state(BusinessState.S0_IDLE))

    # ---------- 营销推荐查询 ----------
    def _trigger_script_query(self):
        """业务查询结果已发布，异步触发营销推荐查询"""
        self.get_logger().info(f"触发营销推荐查询，手机号: {self.phone_number}")
        self.pub_api.publish(String(data=json.dumps({
            "func_name": "script_active_query",
            "params_json": json.dumps({
                "userInfo": {"msisdn": self.phone_number},
                "qryInfo": {"pageInfo": {"busiClssID": "0", "pageNum": 1, "pageSize": 3}}
            })
        })))

    def _handle_script_query_result(self, code, message, data_json):
        """处理营销推荐查询结果，单独通过 page_switch 发布"""
        if code == 0 and data_json.get("activity_list"):
            activity_list_json = json.dumps(data_json, ensure_ascii=False)
            script_page_data = json.dumps({
                "page": "script_active_query_result",
                "detail": activity_list_json
            }, ensure_ascii=False)
            self.get_logger().info(f"发布营销推荐结果: {script_page_data}")
            self.pub_ui.publish(String(data=script_page_data))
        else:
            self.get_logger().warning(f"营销推荐查询无有效数据: code={code}, message={message}")

def main(args=None):
    rclpy.init(args=args)
    node = BusinessFlowNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
