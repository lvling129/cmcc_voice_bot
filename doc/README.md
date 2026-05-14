# 版本变更

## 1. 唤醒词抛出字段变更

因为唤醒引擎的变更，导致唤醒字段有所区别，分为以下两种类型：

### wakeup（不带角度，先抛出）
```json
{
  "msg_type": "wakeup",
  "params": {
    "keyword": "xiao3-fei1-xiao3-fei1",
    "keyword_type": "main",
    "start_ms": 2790,
    "end_ms": 3530,
    "score": 1877,
    "threshold": 1533,
    "beam": 0,
    "physical": 0,
    "angle": 0,
    "power": 0.00,
    "snr": 0.00,
    "power_td": 0.00
  }
}
```

### wakeup_detail（带角度，后抛出）
```json
{
  "msg_type": "wakeup_detail",
  "params": {
    "keyword": "xiao3-fei1-xiao3-fei1",
    "keyword_type": "main",
    "start_ms": 2760,
    "end_ms": 3520,
    "score": 1944,
    "threshold": 1533,
    "beam": 1,
    "physical": 1,
    "angle": 81,
    "power": 36780912640.00,
    "snr": 0.00,
    "power_td": 0.00
  }
}
```

**说明：**
- `msg_type` 代表此次的唤醒有没有带角度
- `wakeup` 不带角度，先抛出
- `wakeup_detail` 带角度，后抛出
- **注意：** 自定义唤醒词（如"你好小赛"）的 `keyword` 字段为 UTF-8 中文，和以往不同

### 如何替换唤醒词

**配置文件路径：** `resource/vtn/res/vtn/vtn.ini`

**配置项：**
```ini
res_identifier = xsxs
```

**说明：**
- `xsxs` 为 `ivw_3.17.12` 目录下的文件夹名称
- 具体唤醒词资源请联系技术支持获取

---

## 2. 参数变化

### 摄像头剪裁参数
以下参数已经生效：

```json
"cam_clip_left": 0,
"cam_clip_right": 0,
"cam_clip_top": 0,
"cam_clip_bottom": 0
```

设置非 0 值会在人脸回调的 JSON 结果中，和 `list` 同级别新增 `format` 字段，其中包含了 `image_h` / `image_w`。

**回调 JSON 示例：**
```json
{
  "format": {
    "image_w": 1280,
    "image_h": 720
  },
  "list": [
    {
    }
  ]
}
```

**使用示例：**
```c
cJSON *format = cJSON_GetObjectItem(root, "format");
if (format == nullptr)
{
    std::cerr << "No format object found!" << std::endl;
    cJSON_Delete(root);
    return;
}
if (cJSON_IsNumber(cJSON_GetObjectItem(format, "image_w")) && 
    cJSON_IsNumber(cJSON_GetObjectItem(format, "image_h")))
{
    image_w = cJSON_GetObjectItem(format, "image_w")->valueint;
    image_h = cJSON_GetObjectItem(format, "image_h")->valueint;
}
```

**字段说明：**
- `image_w`：实际剪裁后的宽度
- `image_h`：实际剪裁后的高度

### 自动降级参数
```json
"auto_lower_rank": 0
```

**参数说明：**
- `0`：没有唇形立即不交互
- `1`：没有唇形但是有人脸就可以交互
- `2`：没有人脸但是有人体就可以交互
- `3`：不限制（**建议慎重使用**）


