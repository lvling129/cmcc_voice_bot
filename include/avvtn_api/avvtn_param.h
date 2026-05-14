#ifndef _AVVTN_PARAM_H
#define _AVVTN_PARAM_H

#include <stddef.h>

#if !defined(__WINDOWS__) && (defined(WIN32) || defined(WIN64) || defined(_MSC_VER) || defined(_WIN32))
#define __WINDOWS__
#endif

#ifdef __WINDOWS__
#define _AVVTN_CDECL             __cdecl
#define _AVVTN_STDCALL           __stdcall
#define AVVTN_CALLING_CONVENTION _AVVTN_CDECL

/* export symbols by default, this is necessary for copy pasting the C and header file */
#if !defined(AVVTN_HIDE_SYMBOLS) && !defined(AVVTN_IMPORT_SYMBOLS) && !defined(AVVTN_EXPORT_SYMBOLS)
#define AVVTN_EXPORT_SYMBOLS
#endif

#if defined(AVVTN_HIDE_SYMBOLS)
#define AVVTN_PUBLIC(type) type AVVTN_CALLING_CONVENTION
#elif defined(AVVTN_EXPORT_SYMBOLS)
#define AVVTN_PUBLIC(type) __declspec(dllexport) type AVVTN_CALLING_CONVENTION
#elif defined(AVVTN_IMPORT_SYMBOLS)
#define AVVTN_PUBLIC(type) __declspec(dllimport) type AVVTN_CALLING_CONVENTION
#endif
#else /* !__WINDOWS__ */
#define _AVVTN_CDECL
#define _AVVTN_STDCALL
#define AVVTN_CALLING_CONVENTION _AVVTN_CDECL

#if (defined(__GNUC__) || defined(__SUNPRO_CC) || defined(__SUNPRO_C)) && !defined(AVVTN_API_VISIBILITY)
#define AVVTN_PUBLIC(type) __attribute__((visibility("default"))) type
#else
#define AVVTN_PUBLIC(type) type
#endif
#endif    // __WINDOWS__

/* status code for avvtn function */
typedef enum
{
    /* everything is all right */
    AVVTN_STATUS_SUCCESS = 0,
    /* general fail */
    AVVTN_STATUS_GENERAL_FAIL,
    /* init failed */
    AVVTN_STATUS_INIT_FAILED,
    /* init failed */
    AVVTN_STATUS_DESTROY_FAILED,
    /* no authorization, contact your business partner */
    AVVTN_STATUS_NO_AUTHORIZATION,
    /* param invalid, check your param */
    AVVTN_STATUS_INVALID_PARAM,
    /* param value invalid, check your param value */
    AVVTN_STATUS_INVALID_PARAM_VALUE,
    /* illegal state, check your call flow */
    AVVTN_STATUS_ILLEGAL_STATE,
    /* illegal data value, check your input data */
    AVVTN_STATUS_INVALID_DATA_VALUE,
    /* count for avvtn_status */
    AVVTN_STATUS_COUNT,
} avvtn_status_code_e;

/*
 * callback type for vtn.
 * notice for Android developer: should sync with VtnApiJni.java
 */
typedef enum
{
    // reserved type. in general, it won't triggered.
    AVVTN_CALLBACK_TYPE_RESERVED = 0,

    // for auth result
    AVVTN_CALLBACK_TYPE_AUTHORIZATION = 6,

    // for wake
    AVVTN_CALLBACK_TYPE_AUDIO_WAKE = 10,

    // for recognition: also called iat
    AVVTN_CALLBACK_TYPE_AUDIO_REC = 30,
    // for AEC audio
    AVVTN_CALLBACK_TYPE_AUDIO_CAE,

    // for face recognition
    AVVTN_CALLBACK_TYPE_FACE_REC = 40,

} avvtn_callback_type_e;

/* callback data for avvtn_api */
typedef struct
{
    // callback type
    avvtn_callback_type_e type;
    // body data. in general, this is string
    void *data;
    // size of data
    int data_size;
    // extra param
    void *param;
    // size of param
    int param_size;
} avvtn_callback_data_t;

/* callback pack for avvtn_api */
typedef struct
{
    /* user_data that will be passed to handler function param. */
    void *user_data;
    /* function prototype of handle callback */
    int(AVVTN_CALLING_CONVENTION *handler)(avvtn_callback_data_t *data_p, void *user_data);
} avvtn_callback_pack_t;

/* param for avvtn_api_init */
typedef struct
{
    // [in] in params.
    const char *input;

    // [in] user callback pack.
    avvtn_callback_pack_t callback;

} avvtn_init_param_t;

#define MODULE_AVVTN_TYPE_BASE 100

/* avvtn_api interactive type */
typedef enum
{
    // reserved
    AVVTN_INTERACT_TYPE_RESERVED = 0,

    //  general param action.
    //  the supported parameters can be found in the "AVVTN_PARAM_ACTION_XXX" above.
    //    generally speaking, no need to use this parameter,
    //    please use the parameters specified below.
    AVVTN_INTERACT_TYPE_PARAM_ACTION = MODULE_AVVTN_TYPE_BASE,

    // set vtn beam
    AVVTN_INTERACT_TYPE_SET_BEAM = MODULE_AVVTN_TYPE_BASE + 10,

    // feed audio
    AVVTN_INTERACT_TYPE_FEED_AUDIO = MODULE_AVVTN_TYPE_BASE + 40,
    // feed video
    AVVTN_INTERACT_TYPE_FEED_VIDEO,

    // evaluate wake word
    AVVTN_INTERACT_TYPE_EVALUATE_KEYWORD = MODULE_AVVTN_TYPE_BASE + 50,
    // generate wake word
    AVVTN_INTERACT_TYPE_GENERATE_KEYWORD,
    // add wake word
    AVVTN_INTERACT_TYPE_ADD_KEYWORD,
    // remove wake word
    AVVTN_INTERACT_TYPE_REMOVE_KEYWORD,

    // set param
    AVVTN_INTERACT_TYPE_SET_PARAM = MODULE_AVVTN_TYPE_BASE + 60,

} avvtn_interact_type_e;

/* interact params for avvtn_interact_info_t */
typedef struct
{
    // size of str
    size_t str_size;
    // string pointer
    char *str;

    // size of raw
    size_t raw_size;
    // raw data pointer
    void *raw;
} avvtn_interact_param_t;

/**
 * @brief output type of interact result,
 */
typedef enum
{
    AVVTN_INTERACT_OUTPUT_TYPE_NONE = 0,
    AVVTN_INTERACT_OUTPUT_TYPE_STR  = 1,
    AVVTN_INTERACT_OUTPUT_TYPE_RAW  = (1 << 1),
} avvtn_interact_output_type_e;

/**
 * @brief interact info for avvvtn
 *
 * note:
 * 这里设计成 in/out 参数, 并用 string + raw 参数搭配的这种组合 原因如下：
 *   0. 标准化输入输出: 所有交互都通过这种模式规范化输入输出.
 *   1. 兼容 Android jni 层操作: 方便 jni 层透传输入输出数据, 无需再做接口业务数据转换和对接,
 *      否则对于每种 interact_type 还需额外的 jni 对接开发工作量.
 *   2. 方便后面需求扩展: string + raw 这种参数组合基本上可以覆盖绝大数交互场景的需求，
 *      新增需求无需改动接口, 只需对 string 或者 raw 内容做扩展即可.
 *      str: 一般放交互参数信息, 大多数情况下是个 json string.
 *      raw: 一般配合 json 作为补充, 比如写音频这个交互类型, 音频就放在 raw 参数里指向的内存.
 *
 * 缺点: 开发者得知道每种交互类型的输入输出是什么，按照协议组装、解析交互数据.
 *       不过话说回来, 开发者本来就得理解每种交互的输入/输出是什么.
 *
 * FAQ:
 *  Q:  为什么不把交互类型(avvtn_interact_type_e type) 放到 in.str 参数json里作为一个字段呢? 额外放一个成员显得突兀.
 *  A:  是为了优化性能: 高频交互操作是写音频, 若把交互类型放到 str 里势必会导致每次都需去解析json获取type字段, 导致性能下降.
 *
 *  Q:  为什么交互输出参数 (avvtn_interact_param_t out) 的内存也是由调用者分配，调用者该分配多少呢?
 *  A:  1. 调用者分配内存可以复用参数及内存，另外引擎内部不好管理输出的内存，不知道调用者何时不需要这块内存，
 *         所以最终决定由调用者分配内存，引擎负责将输出的结果拷贝到输出参数(out)的内存里. 另外其实带参数交互的情况也不多.
 *      2. 具体分配多少内存这个没有个规定值, 得看具体的交互类型，通常建议 4KB 就足够了, 大多参数交互输出的是 json string.
 *         另外即使调用者分配的内存不够, 接口也会抛出对应的错误码和日志信息, 可以根据错误码来扩大交互输出参数的内存.
 *      3. 还有一点提醒下开发者: 交互参数 in/out 里的 str.size 和 raw.size 都是字节大小, 告诉引擎的大小不能比实际分配的大,
 *         否则可能会导致引擎访问这块内存越界, 造成不可挽回的内存崩溃问题.
 *
 *  Q:  结构体 avvtn_interact_info_t.with_out 成员参数有什么作用?
 *  A:  结构体成员 with_out 在交互前(调用 interact 接口前)应该置为0(AVVTN_INTERACT_OUTPUT_TYPE_NONE),
 *      这个参数会在引擎交互接口被赋值, 用于指示当前输出的结果包含哪些信息, 可以用位与的方式判断输出结果的数据类型.
 *      1. 若 (with_out & AVVTN_INTERACT_OUTPUT_TYPE_STR) 不为 0, 则代表 out.str 有数据可以被读取, 数据大小为 out.str_size
 *      2. 若 (with_out & AVVTN_INTERACT_OUTPUT_TYPE_RAW) 不为 0, 则代表 out.raw 有数据可以被读取, 数据大小为 out.raw_size
 *     至于这个 out.str 和 out.raw 里面代表的信息内容, 根据不同的交互类型有不同的含义, 具体的参见示例sample代码.
 *
 */
typedef struct
{
    // [in] interact type
    avvtn_interact_type_e type;

    // [in] interact param.
    avvtn_interact_param_t in;

    // [out] indicates whether there is an output.
    //       see type on avvtn_interact_output_type_e.
    //       notice: maybe multi-type data will be outputted.
    int with_out;

    // [out] result of interact.
    //       notice: caller must provide memory.
    avvtn_interact_param_t out;
} avvtn_interact_info_t;

#endif