#include "echo/config.h"
#include <json-c/json.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

void echo_config_defaults(echo_config_t *config) {
    memset(config, 0, sizeof(*config));
    strcpy(config->name, "echo_mate_rv1106");
    strcpy(config->bind_address, "0.0.0.0");
    strcpy(config->gpio_root, "/sys/class/gpio");
    strcpy(config->audio_device, "plughw:0,0");
    strcpy(config->camera_program, "/usr/bin/echo-camera");
    strcpy(config->frame_path, "/tmp/echo-litepanel/frame.jpg");
    strcpy(config->cloud_file, "/userdata/echo-litepanel/cloud.json");
    config->tcp_port = 9000; config->discovery_port = 9001;
    config->http_port = 9002; config->stream_port = 9003;
    config->audio_enabled = config->camera_enabled = true;
}
static int string_field(struct json_object *root, const char *name, char *dst, size_t size) {
    struct json_object *item;
    if (!json_object_object_get_ex(root, name, &item)) return 0;
    if (!json_object_is_type(item, json_type_string)) return -1;
    size_t length = json_object_get_string_len(item);
    const char *text = json_object_get_string(item);
    if (length >= size || strlen(text) != length) return -1;
    memcpy(dst, text, length + 1);
    return 0;
}
int echo_cloud_config_load(const char *path, echo_cloud_config_t *config) {
    if (access(path, F_OK)) return 1;
    struct json_object *root = json_object_from_file(path), *item;
    if (!root || !json_object_is_type(root, json_type_object)) {
        if (root) json_object_put(root);
        return -1;
    }
    memset(config, 0, sizeof(*config));
    strcpy(config->device_id, "echo-mate001");
    strcpy(config->ca_file, "/opt/echo-litepanel/certs/ca-bundle.crt");
    config->tls = true; config->camera_fps = 2;
    int rc = string_field(root, "host", config->host, sizeof(config->host)) |
             string_field(root, "device_id", config->device_id, sizeof(config->device_id)) |
             string_field(root, "username", config->username, sizeof(config->username)) |
             string_field(root, "password", config->password, sizeof(config->password)) |
             string_field(root, "ca_file", config->ca_file, sizeof(config->ca_file));
    if (json_object_object_get_ex(root, "tls", &item)) {
        if (!json_object_is_type(item, json_type_boolean)) rc = -1;
        else config->tls = json_object_get_boolean(item);
    }
    config->port = config->tls ? 8883 : 1883;
    if (json_object_object_get_ex(root, "port", &item)) {
        int port = json_object_get_int(item);
        if (!json_object_is_type(item, json_type_int) || port < 1 || port > 65535) rc = -1;
        else config->port = port;
    }
    if (json_object_object_get_ex(root, "camera_fps", &item)) {
        double fps = json_object_get_double(item);
        if ((!json_object_is_type(item, json_type_int) && !json_object_is_type(item, json_type_double)) ||
            !isfinite(fps) || fps < 0 || fps > 5) rc = -1;
        else config->camera_fps = fps;
    }
    if (!config->device_id[0] || strpbrk(config->device_id, "/+#")) rc = -1;
    json_object_put(root);
    if (rc) return -1;
    return config->host[0] ? 0 : 1;
}
