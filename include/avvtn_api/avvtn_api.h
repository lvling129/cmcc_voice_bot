#ifndef _AVVTN_API_H
#define _AVVTN_API_H

#include "avvtn_param.h"

typedef struct AvvtnImpl *avvtn_handle;

#define AVVTN_API_LIST(func)         \
    func(avvtn_api_get_version)      \
        func(avvtn_api_init)         \
            func(avvtn_api_interact) \
                func(avvtn_api_destroy)

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief get version
 *
 * @return const char*  version string
 */
AVVTN_PUBLIC(const char *)
avvtn_api_get_version();
typedef const char *(AVVTN_CALLING_CONVENTION *proc_avvtn_api_get_version)();

/**
 * @brief init api by param
 *
 * @param handle_p pointer of avvtn_handle
 * @param param_p pointer of avvtn_init_param_t
 * @return avvtn_status_code_e of init status
 */
AVVTN_PUBLIC(avvtn_status_code_e)
avvtn_api_init(avvtn_handle *handle_p, avvtn_init_param_t *param_p);
typedef avvtn_status_code_e(AVVTN_CALLING_CONVENTION *proc_avvtn_api_init)(avvtn_handle *handle_p, avvtn_init_param_t *param_p);

/**
 * @brief interact with api
 *
 * @param handle avvtn_handle
 * @param info_p pointer of interact info
 * @return avvtn_status_code_e of interact result status
 */
AVVTN_PUBLIC(avvtn_status_code_e)
avvtn_api_interact(avvtn_handle handle, avvtn_interact_info_t *info_p);
typedef avvtn_status_code_e(AVVTN_CALLING_CONVENTION *proc_avvtn_api_interact)(avvtn_handle handle, avvtn_interact_info_t *info_p);

/**
 * @brief destroy api
 *
 * @param handle avvtn_handle
 * @return avvtn_status_code_e of destroy result
 */
AVVTN_PUBLIC(avvtn_status_code_e)
avvtn_api_destroy(avvtn_handle handle);
typedef avvtn_status_code_e(AVVTN_CALLING_CONVENTION *proc_avvtn_api_destroy)(avvtn_handle handle);

#ifdef __cplusplus
}
#endif
#endif