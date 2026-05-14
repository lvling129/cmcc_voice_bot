#include "aiui_wapper.h"
#include "utils/Logger.hpp"
#include "ros2/ros_manager.hpp"

// TtsHelperListener
void TtsHelperListener::onText(const StreamNlpTtsHelper::OutTextSeg &textSeg)
{
    if (textSeg.isBegin() || textSeg.isEnd())
    {
        if (aiui_pcm_player_get_state() != PCM_PLAYER_STATE_STARTED)
        {
            aiui_pcm_player_start();
        }
        if (textSeg.isBegin())
        {
            aiui_pcm_player_clear();
        }
    }
    // 调用合成 - 参考demo中TtsHelperListener::onText的实现
    LOG_INFO("调用合成:");
    aiui_wrapper_ptr_->StartTTS(textSeg.mText, textSeg.mTag);
    return;
}

void TtsHelperListener::onFinish(const std::string &fullText)
{
    LOG_INFO("tts, fullText = %s", fullText.c_str());
    return;
}

void TtsHelperListener::onTtsData(const Json::Value &bizParamJson, const char *audio, int len)
{
    const Json::Value &data    = (bizParamJson["data"])[0];
    const Json::Value &content = (data["content"])[0];
    int dts                    = content["dts"].asInt();
    int progress               = content["text_percent"].asInt();

    LOG_DEBUG("将合成数据写入播放器");
    // 将合成数据写入播放器
    aiui_pcm_player_write(0, audio, len, dts, progress);
    return;
}

// AIUIListener
int AIUIListener::Init(const aiui_callback_pack_t &aiui_callback_pack)
{
    LOG_INFO("初始化AIUIListener");
    int ret = 0;

    aiui_callback_pack_ = aiui_callback_pack;

    LOG_INFO("创建内置的pcm播放器, 并初始化，设置回调，启动起来");
    // 创建内置的pcm播放器，并初始化，设置回调，启动起来
    ret = aiui_pcm_player_create();
    if (ret != 0)
    {
        std::cout << "aiui_pcm_player_create failed" << std::endl;
        LOG_ERROR("内置的pcm播放器创建失败");
        return -1;
    }

    LOG_INFO("获取音频输出设备数量");
    // 获取输出设备数量
    int count = aiui_pcm_player_get_output_device_count();
    for (int i = 0; i < count; i++)
    {
        // 打印输出设备信息
        std::cout << "pcm player index: " << i << " device name: " << aiui_pcm_player_get_device_name(i) << std::endl;
        LOG_INFO("pcm player index: %d, device name: %s", i, aiui_pcm_player_get_device_name(i));
    }

    LOG_INFO("选择默认播放设备进行初始化");
    // 初始化播放器，你应该根据上面打印的设备信息，选择一个设备，然后初始化，当前默认-1代表了默认的播放设备索引
    // 如果默认设备无法播放，请根据上述打印结果选择其他设备，并初始化
    ret = aiui_pcm_player_init(-1);
    if (ret != 0)
    {
        LOG_ERROR("内置的pcm播放器初始化失败");
        std::cout << "aiui_pcm_player_init failed" << std::endl;
        return -1;
    }

    // 创建TTS播放辅助类
    tts_helper_ptr_ = std::make_shared<StreamNlpTtsHelper>(std::make_shared<TtsHelperListener>(aiui_wrapper_ptr_));
    // 设置TTS最小文本长度
    tts_helper_ptr_->setTextMinLimit(20);
    LOG_INFO("初始化AIUIListener成功");
    return 0;
}

int AIUIListener::Destory()
{
    aiui_pcm_player_destroy();
    return 0;
}

void AIUIListener::onEvent(const IAIUIEvent &event)
{
    if (aiui_callback_pack_.handler)
    {
        aiui_callback_pack_.handler(aiui_callback_pack_.user_data, event);
    }
    else
    {
        std::cout << "AIUI callback function is not set" << std::endl;
        LOG_ERROR("AIUI callback function is not set");
    }
    return;
}

// AiuiWrapper
int AiuiWrapper::Init(const aiui_init_param_t &aiui_init_param)
{
    aiui_init_param_ = aiui_init_param;

    // 初始化设置
    initSetting();

    LOG_INFO("创建AIUI监听器Listener");
    // 创建监听器
    listener_ = std::make_shared<AIUIListener>(this);
    int ret   = listener_->Init(aiui_init_param_.callback);
    if (ret != 0)
    {
        std::cout << "AIUIListener Init failed" << std::endl;
        LOG_ERROR("AIUIListener Init failed");
        return -1;
    }

    // 读取配置文件
    std::string aiui_params;
    if (!aiui_init_param_.param.cfg_path.empty())
    {
        LOG_INFO("读取AIUI配置文件: %s", aiui_init_param_.param.cfg_path.c_str());
        std::ifstream config_file(aiui_init_param_.param.cfg_path, std::ios_base::in | std::ios::binary);
        if (!config_file.is_open())
        {
            std::cout << "Error open config file: " << aiui_init_param_.param.cfg_path << std::endl;
            LOG_ERROR("Error open config file: %s", aiui_init_param_.param.cfg_path.c_str());
            return -1;
        }
        aiui_params = std::string((std::istreambuf_iterator<char>(config_file)), std::istreambuf_iterator<char>());
        config_file.close();
    }

    // 解析JSON配置
    Json::Value param_json;
    Json::Reader reader;
    if (!reader.parse(aiui_params, param_json, false))
    {
        std::cout << "Parse config error: " << reader.getFormattedErrorMessages() << std::endl;
        LOG_ERROR("Parse config error: %s", reader.getFormattedErrorMessages().c_str());
        return -1;
    }

    LOG_INFO("创建AIUI代理Agent");
    // 创建AIUI代理
    aiui_agent_ = IAIUIAgent::createAgent(param_json.toString().c_str(), listener_.get(), GetMacAddress().c_str());
    if (!aiui_agent_)
    {
        std::cout << "Create AIUI agent failed" << std::endl;
        LOG_ERROR("Create AIUI agent failed");
        return -1;
    }

    std::cout << "AiuiWrapper Init success" << std::endl;
    return 0;
}

int AiuiWrapper::Destory()
{
    if (aiui_agent_)
    {
        aiui_agent_->destroy();
        aiui_agent_ = nullptr;
    }

    if (listener_)
    {
        listener_->Destory();
        listener_.reset();
    }

    return 0;
}

void AiuiWrapper::Wakeup()
{
    LOG_INFO("发送唤醒命令给AIUI, 默认清除唤醒之前的数据");
    // 可以通过clear_data来控制是否要清除唤醒之前的数据（默认会清除），清除则唤醒之前的会话结果（tts除外）会被丢弃从而不再继续抛出
    sendAIUIMessage(AIUIConstant::CMD_WAKEUP, 0, 0, "clear_data=true");
    return;
}

void AiuiWrapper::ResetWakeup()
{
    LOG_INFO("发送开始Reset唤醒命令给AIUI");
    sendAIUIMessage(AIUIConstant::CMD_RESET_WAKEUP);
    return;
}

void AiuiWrapper::Start()
{
    LOG_INFO("发送开始命令给AIUI");
    sendAIUIMessage(AIUIConstant::CMD_START);
    return;
}

void AiuiWrapper::Stop()
{
    LOG_INFO("发送停止命令给AIUI");
    sendAIUIMessage(AIUIConstant::CMD_STOP);
    return;
}

void AiuiWrapper::ResetAIUI()
{
    LOG_INFO("发送Reset命令给AIUI");
    sendAIUIMessage(AIUIConstant::CMD_RESET, 0, 0, "");
    return;
}

void AiuiWrapper::WriteText(const std::string &text, bool needWakeup)
{
    LOG_INFO("发送文本Text给AIUI");
    AIUIBuffer textData = aiui_create_buffer_from_data(text.c_str(), text.length());

    if (needWakeup)
    {
        sendAIUIMessage(AIUIConstant::CMD_WRITE, 0, 0, "data_type=text,pers_param={\"uid\":\"\"}", textData);
    }
    else
    {
        sendAIUIMessage(AIUIConstant::CMD_WRITE, 0, 0, "data_type=text,need_wakeup=false", textData);
    }
    return;
}

void AiuiWrapper::WriteAudioFromLocal(bool repeat)
{
    LOG_INFO("发送保存的音频文件给AIUI");
    if (!aiui_agent_) return;

    const char *TEST_AUDIO_PATH = "/home/lzw/code/c++/work/demo/aiui_myself/res/aiui/audio/test.pcm";
    std::ifstream testData(TEST_AUDIO_PATH, std::ios::in | std::ios::binary);

    if (testData.is_open())
    {
        testData.seekg(0, std::ios::end);
        int total = testData.tellg();
        testData.seekg(0, std::ios::beg);

        char *audio = new char[total];
        testData.read(audio, total);
        testData.close();

        int offset         = 0;
        int left           = total;
        const int frameLen = 1280;
        char buff[frameLen];

        while (true)
        {
            if (left < frameLen)
            {
                if (repeat)
                {
                    offset = 0;
                    left   = total;
                    continue;
                }
                else
                {
                    break;
                }
            }

            memset(buff, '\0', frameLen);
            memcpy(buff, audio + offset, frameLen);

            offset += frameLen;
            left -= frameLen;

            // frameData内存会在Message在内部处理完后自动release掉
            WriteAudio(buff, frameLen, false);

            // 必须暂停一会儿模拟人停顿，太快的话后端报错。1280字节16k采样16bit编码的pcm数据对应40ms时长
            AIUI_SLEEP(40);
        }

        // 音频写完后，要发CMD_STOP_WRITE停止写入消息
        WriteAudio(nullptr, 0, true);

        delete[] audio;
        std::cout << "write audio finish" << std::endl;
    }
    else
    {
        std::cout << "open file failed, path=" << TEST_AUDIO_PATH << std::endl;
    }
    return;
}

void AiuiWrapper::WriteAudio(const char *data, const int len, bool is_stop)
{
    if (is_stop)
    {
        LOG_DEBUG("停止发送音频数据给AIUI");
        sendAIUIMessage(AIUIConstant::CMD_STOP_WRITE, 0, 0, "data_type=audio");
    }
    else
    {
        LOG_DEBUG("发送识别到的音频数据给AIUI");
        AIUIBuffer audioData = aiui_create_buffer_from_data(data, len);
        sendAIUIMessage(AIUIConstant::CMD_WRITE, 0, 0, "data_type=audio,tag=audio-tag", audioData);
    }
    return;
}

void AiuiWrapper::StartRecordAudio()
{
    LOG_INFO("发送开始录音命令给AIUI");
    sendAIUIMessage(AIUIConstant::CMD_START_RECORD, 0, 0, "data_type=audio,pers_param={\"uid\":\"\"},tag=record-tag");
    return;
}

void AiuiWrapper::StopRecordAudio()
{
    LOG_INFO("发送停止录音命令给AIUI");
    sendAIUIMessage(AIUIConstant::CMD_STOP_RECORD);
    return;
}

void AiuiWrapper::StartTTS(const std::string &text, const std::string &tag)
{
    LOG_INFO("发送开始TTS命令给AIUI");
    AIUIBuffer textData = aiui_create_buffer_from_data(text.c_str(), text.length());

    //不设置发言人 默认发言人为aiui.cfg中配置的
    std::string params;
    if (!tag.empty())
    {
        params.append(",tag=").append(tag);
    }

    // 使用aiui.cfg中配置的发音人合成
    sendAIUIMessage(AIUIConstant::CMD_TTS, AIUIConstant::START, 0, params.c_str(), textData);
    return;
}

void AiuiWrapper::StartHTS(const std::string &text, const std::string &tag)
{
    LOG_INFO("发送开始HTS命令给AIUI");
    AIUIBuffer textData = aiui_create_buffer_from_data(text.c_str(), text.length());

    // 超拟人合成需要先给发音人开通授权，再设置scene=IFLYTEK.hts
    // 口语化等级oral_level: high, mid（默认值）, low
    // 情感强度emotion_scale: [-20, 20]，默认值: 0
    // 情感类型emotion: 0（中立，默认）, 1（调皮）, 2（安慰）, 3（可爱）, 4（鼓励）, 5（高兴）, 6（抱歉）, 7（撒娇）, 8（宠溺）, 9（严肃）
    // 10（困惑）, 11（害怕）, 12（悲伤）, 13（生气）
    std::string params = "voice_name=x4_lingxiaoxuan_oral,scene=IFLYTEK.hts,oral_level=mid,emotion_scale=0,emotion=0";
    if (!tag.empty())
    {
        params.append(",tag=").append(tag);
    }

    sendAIUIMessage(AIUIConstant::CMD_TTS, AIUIConstant::START, 0, params.c_str(), textData);
    return;
}

void AiuiWrapper::StartTTSUrl(const std::string &text)
{
    AIUIBuffer textData = aiui_create_buffer_from_data(text.c_str(), text.length());
    // 使用发音人x2_xiaojuan合成，返回url
    sendAIUIMessage(AIUIConstant::CMD_TTS, AIUIConstant::START, 0, "text_encoding=utf-8,tts_res_type=url,vcn=x2_xiaojuan", textData);
    return;
}

void AiuiWrapper::BuildEsrGrammar()
{
    // 读取语法文件
    std::ifstream grammar_file("AIUI/esr/message.fsa", std::ios_base::in | std::ios::binary);
    if (!grammar_file.is_open())
    {
        std::cout << "Error open grammar file" << std::endl;
        return;
    }

    std::string grammar((std::istreambuf_iterator<char>(grammar_file)), std::istreambuf_iterator<char>());
    grammar_file.close();

    sendAIUIMessage(AIUIConstant::CMD_BUILD_GRAMMAR, 0, 0, grammar.c_str());
    return;
}

void AiuiWrapper::CleanDialogHistory()
{
    std::cout << "cleanDialogHistory" << std::endl;
    sendAIUIMessage(AIUIConstant::CMD_CLEAN_DIALOG_HISTORY);
    return;
}

void AiuiWrapper::SyncSchemaData(int type)
{
    // 通讯录同步示例内容
    std::string SYNC_CONTACT_CONTENT = R"({"name":"刘得华", "phoneNumber":"13512345671"})"
                                       "\n"
                                       R"({"name":"张学诚", "phoneNumber":"13512345672"})"
                                       "\n"
                                       R"({"name":"张右兵", "phoneNumber":"13512345673"})"
                                       "\n"
                                       R"({"name":"吴羞波", "phoneNumber":"13512345674"})"
                                       "\n"
                                       R"({"name":"黎晓", "phoneNumber":"13512345675"})";

    std::string dataStrBase64 = Base64Util::encode(SYNC_CONTACT_CONTENT);

    Json::Value syncSchemaJson;
    Json::Value dataParamJson;

    // 设置id_name为uid，即用户级个性化资源
    dataParamJson["id_name"] = "uid";
    // 设置res_name为联系人
    dataParamJson["res_name"] = "IFLYTEK.telephone_contact";

#if AIUI_VER == 2 || AIUI_VER == 3
    // aiui开放平台的命名空间，在「技能工作室-我的实体-动态实体密钥」中查看
    dataParamJson["name_space"] = "OS13360977719";
#endif

    syncSchemaJson["param"] = dataParamJson;
    if (AIUIConstant::SYNC_DATA_SCHEMA == type || AIUIConstant::SYNC_DATA_UPLOAD == type)
    {
        syncSchemaJson["data"] = dataStrBase64;
    }

    std::string jsonStr = syncSchemaJson.toString();

    // 传入的数据一定要为utf-8编码
    AIUIBuffer syncData = aiui_create_buffer_from_data(jsonStr.c_str(), jsonStr.length());

    // 给该次同步加上自定义tag，在返回结果中可通过tag将结果和调用对应起来
    Json::Value paramJson;
    paramJson["tag"] = "sync-tag";

    // 用schema数据同步上传联系人
    // 注：数据同步请在连接服务器之后进行，否则可能失败
    sendAIUIMessage(AIUIConstant::CMD_SYNC, type, 0, paramJson.toString().c_str(), syncData);
    return;
}

#if AIUI_VER == 2 || AIUI_VER == 3
void AiuiWrapper::SyncV2SeeSayData()
{
    const char *TEST_SEE_SAY_PATH = "./AIUI/text/see_say.txt";
    std::ifstream see_say_file(TEST_SEE_SAY_PATH, std::ios_base::in | std::ios::binary);
    if (!see_say_file.is_open())
    {
        std::cout << "Error open see say file: " << TEST_SEE_SAY_PATH << std::endl;
        return;
    }

    std::string seeSayContent((std::istreambuf_iterator<char>(see_say_file)), std::istreambuf_iterator<char>());
    see_say_file.close();

    Json::Value contentJson;
    Json::Reader reader;
    if (!reader.parse(seeSayContent, contentJson, false))
    {
        std::cout << "syncV2SeeSayData parse error! info=" << seeSayContent << std::endl;
        return;
    }

    std::cout << "see say content: " << contentJson.asString() << std::endl;
    // 整个json在进行base64编码
    std::string dataStrBase64 = Base64Util::encode(contentJson.asString());
    Json::Value syncSeeSayJson;
    syncSeeSayJson["data"] = dataStrBase64;
    std::string jsonStr    = syncSeeSayJson.toString();
    AIUIBuffer syncData    = aiui_create_buffer_from_data(jsonStr.c_str(), jsonStr.length());

    // 给该次同步加上自定义tag，在返回结果中可通过tag将结果和调用对应起来
    Json::Value paramJson;
    paramJson["tag"] = "sync_see_say_tag";

    // 注：数据同步请在连接服务器之后进行，否则可能失败
    sendAIUIMessage(AIUIConstant::CMD_SYNC, AIUIConstant::SYNC_DATA_SEE_SAY, 0, paramJson.toString().c_str(), syncData);
    return;
}

void AiuiWrapper::VoiceCloneReg(const std::string &resPath)
{
    std::string resource_path = resPath.empty() ? "./AIUI/audio/voice_clone_1ch24K16bit.pcm" : resPath;

    Json::Value paramJson;
    paramJson["tag"]      = "voice_clone_tag_0";
    paramJson["res_path"] = resource_path;

    std::cout << "上传声音复刻的资源,资源路径: " << resource_path << std::endl;

    // 注：数据同步请在连接服务器之后进行，否则可能失败
    sendAIUIMessage(AIUIConstant::CMD_CLONE_VOICE, AIUIConstant::VOICE_CLONE_REG, 0, paramJson.toString().c_str(), nullptr);
    return;
}

void AiuiWrapper::VoiceCloneDelRes()
{
    std::string resId = voice_clone_resource_id_;
    if (resId.empty())
    {
        // 尝试从文件读取
        std::ifstream res_file("./voice_clone_reg_id.txt", std::ios_base::in | std::ios::binary);
        if (res_file.is_open())
        {
            resId = std::string((std::istreambuf_iterator<char>(res_file)), std::istreambuf_iterator<char>());
            res_file.close();
        }
    }

    if (resId.empty())
    {
        std::cout << "删除声音复刻的资源失败，资源ID为NULL" << std::endl;
        return;
    }

    std::cout << "删除声音复刻的资源,res id = " << resId << std::endl;

    Json::Value paramJson;
    paramJson["tag"]    = "voice_clone_tag_1";
    paramJson["res_id"] = resId;

    // 注：数据同步请在连接服务器之后进行，否则可能失败
    sendAIUIMessage(AIUIConstant::CMD_CLONE_VOICE, AIUIConstant::VOICE_CLONE_DEL, 0, paramJson.toString().c_str(), nullptr);
    return;
}

void AiuiWrapper::VoiceCloneQueryRes()
{
    Json::Value paramJson;
    paramJson["tag"] = "voice_clone_tag_2";

    // 注：数据同步请在连接服务器之后进行，否则可能失败
    sendAIUIMessage(AIUIConstant::CMD_CLONE_VOICE, AIUIConstant::VOICE_CLONE_RES_QUERY, 0, paramJson.toString().c_str(), nullptr);
    return;
}

void AiuiWrapper::StartVoiceCloneTTS(const std::string &text, const std::string &tag)
{
    std::string resId = voice_clone_resource_id_;
    if (resId.empty())
    {
        // 尝试从文件读取
        std::ifstream res_file("./voice_clone_reg_id.txt", std::ios_base::in | std::ios::binary);
        if (res_file.is_open())
        {
            resId = std::string((std::istreambuf_iterator<char>(res_file)), std::istreambuf_iterator<char>());
            res_file.close();
        }
    }

    if (resId.empty())
    {
        std::cout << "请求声音复刻的tts失败，资源ID为NULL" << std::endl;
        return;
    }

    AIUIBuffer textData = aiui_create_buffer_from_data(text.c_str(), text.length());
    // 发言人必须是x5_clone
    std::string params = "voice_name=x5_clone";
    params.append(",res_id=").append(resId);
    if (!tag.empty())
    {
        params.append(",tag=").append(tag);
    }

    sendAIUIMessage(AIUIConstant::CMD_TTS, AIUIConstant::START, 0, params.c_str(), textData);
    return;
}

void AiuiWrapper::AIUILogin()
{
    LOG_INFO("发送Login命令给AIUI");
    sendAIUIMessage(AIUIConstant::CMD_AIUI_LOGIN);
    return;
}
#endif

void AiuiWrapper::QuerySyncSchemaStatus()
{
    LOG_INFO("发送查询同步Schema状态命令给AIUI");
    // 构造查询json字符串，填入同步schema数据返回的sid
    Json::Value queryJson;
    queryJson["sid"] = sync_session_id_;

    // 发送同步数据状态查询消息，设置arg1为schema数据类型，params为查询字符串
    sendAIUIMessage(AIUIConstant::CMD_QUERY_SYNC_STATUS, AIUIConstant::SYNC_DATA_SCHEMA, 0, queryJson.toString().c_str());
    return;
}

void AiuiWrapper::OperateWakeupWord(int op)
{
    LOG_INFO("发送设置唤醒命令给AIUI");
    std::string text;
    if (op != AIUIConstant::CAE_DEL_WAKEUP_WORD)
    {
        // 获取唤醒词名称
        const char *WAKE_WORD_TEXT_PATH = "./AIUI/text/wakeup_wake.txt";
        std::ifstream wake_file(WAKE_WORD_TEXT_PATH, std::ios_base::in | std::ios::binary);
        if (wake_file.is_open())
        {
            text = std::string((std::istreambuf_iterator<char>(wake_file)), std::istreambuf_iterator<char>());
            wake_file.close();
        }
        std::cout << "wakeup word process text: " << text << ", operate type:" << op << std::endl;
        LOG_INFO("wakeup word process text: %s, operate type: %d", text.c_str(), op);
    }
    else
    {
        std::cout << "wakeup word process operate type:" << op << std::endl;
        LOG_INFO("wakeup word process operate type: %d", op);
    }

    sendAIUIMessage(AIUIConstant::CMD_CAE_OPERATE_WAKEUP_WORD, op, 0, text.c_str(), nullptr);
    return;
}

std::string AiuiWrapper::GetMacAddress()
{
#ifdef _WIN32
    ULONG size = 0;
    if (GetAdaptersInfo(nullptr, &size) != ERROR_BUFFER_OVERFLOW || size == 0) return "";

    PIP_ADAPTER_INFO adapterInfo = (PIP_ADAPTER_INFO)malloc(size);
    if (!adapterInfo) return "";

    if (GetAdaptersInfo(adapterInfo, &size) != NO_ERROR)
    {
        free(adapterInfo);
        return "";
    }

    std::string macStr;
    for (PIP_ADAPTER_INFO p = adapterInfo; p; p = p->Next)
    {
        // 跳过没有网关的接口
        if (strcmp(p->GatewayList.IpAddress.String, "0.0.0.0") == 0) continue;

        char buf[32];
        snprintf(buf, sizeof(buf), "%02x:%02x:%02x:%02x:%02x:%02x", p->Address[0], p->Address[1], p->Address[2], p->Address[3], p->Address[4], p->Address[5]);
        macStr = buf;
        break;
    }
    free(adapterInfo);
    return macStr;

#else
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) return "";

    struct ifconf ifc;
    char buf[1024];
    ifc.ifc_len = sizeof(buf);
    ifc.ifc_buf = buf;
    if (ioctl(sock, SIOCGIFCONF, &ifc) < 0)
    {
        close(sock);
        return "";
    }

    struct ifreq *it        = ifc.ifc_req;
    const struct ifreq *end = it + (ifc.ifc_len / sizeof(struct ifreq));
    std::string macStr;

    for (; it != end; ++it)
    {
        struct ifreq ifr;
        strcpy(ifr.ifr_name, it->ifr_name);

        if (ioctl(sock, SIOCGIFFLAGS, &ifr) == 0 && !(ifr.ifr_flags & IFF_LOOPBACK))
        {
            if (ioctl(sock, SIOCGIFHWADDR, &ifr) == 0)
            {
                unsigned char *addr = (unsigned char *)ifr.ifr_hwaddr.sa_data;
                char buf[32];
                snprintf(buf, sizeof(buf), "%02x:%02x:%02x:%02x:%02x:%02x", addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);
                macStr = buf;
                break;
            }
        }
    }
    close(sock);
    return macStr;
#endif
}

void AiuiWrapper::initSetting()
{
#if 0
    // 设置AIUI日志就保存在这个目录
    AIUISetting::setAIUIDir("./");
    // 设置AIUI日志配置目录
    AIUISetting::setMscDir("./msc.cfg");
    // 设置AIUI日志级别
    AIUISetting::setNetLogLevel(LogLevel::aiui_debug);
#endif
    // 生成MAC地址作为序列号
    std::string macStr = GetMacAddress();

    // 为每一个设备设置唯一对应的序列号SN（最好使用设备硬件信息(mac地址，设备序列号等）生成），以便正确统计装机量，
    // 避免刷机或者应用卸载重装导致装机量重复计数
    AIUISetting::setSystemInfo(AIUI_KEY_SERIAL_NUM, macStr.c_str());
    LOG_INFO("设备序列号SN = %s", macStr.c_str());
    return;
}

void AiuiWrapper::sendAIUIMessage(int cmd, int arg1, int arg2, const char *params, AIUIBuffer data)
{
    if (!aiui_agent_) return;
    IAIUIMessage *msg = IAIUIMessage::create(cmd, arg1, arg2, params, data);
    aiui_agent_->sendMessage(msg);
    msg->destroy();
    return;
}