#include "mqtt_publisher.hpp"

#include <mosquitto.h>

#include <utility>

#include "log.hpp"

namespace {
constexpr int kKeepaliveSeconds = 30;
constexpr unsigned kReconnectMinSeconds = 1;
constexpr unsigned kReconnectMaxSeconds = 30;
}  // namespace

MqttPublisher::MqttPublisher(std::string host, int port, std::string client_id)
    : host_(std::move(host)), port_(port), client_id_(std::move(client_id)) {}

MqttPublisher::~MqttPublisher() {
    stop();
    if (mosq_ != nullptr) {
        mosquitto_destroy(mosq_);
    }
}

bool MqttPublisher::start() {
    mosq_ = mosquitto_new(client_id_.c_str(), true, this);
    if (mosq_ == nullptr) {
        log_error("mqtt: mosquitto_new failed");
        return false;
    }
    mosquitto_connect_callback_set(mosq_, &MqttPublisher::on_connect);
    mosquitto_disconnect_callback_set(mosq_, &MqttPublisher::on_disconnect);
    // Exponential backoff between reconnect attempts: 1 s, 2 s, 4 s ... 30 s.
    mosquitto_reconnect_delay_set(mosq_, kReconnectMinSeconds, kReconnectMaxSeconds, true);

    // Start the network thread BEFORE connecting. In this order the thread
    // owns the connection attempt and keeps retrying if the broker is not up
    // yet; in the other order a refused first attempt is never retried.
    int rc = mosquitto_loop_start(mosq_);
    if (rc != MOSQ_ERR_SUCCESS) {
        log_error(std::string("mqtt: loop_start failed: ") + mosquitto_strerror(rc));
        return false;
    }
    rc = mosquitto_connect_async(mosq_, host_.c_str(), port_, kKeepaliveSeconds);
    if (rc != MOSQ_ERR_SUCCESS) {
        log_error("mqtt: initial connect to " + host_ + ":" + std::to_string(port_) +
                  " failed (" + mosquitto_strerror(rc) + "), will retry");
    }
    running_ = true;
    return true;
}

bool MqttPublisher::publish(const std::string &topic, const std::string &payload) {
    if (!connected_) {
        return false;
    }
    int rc = mosquitto_publish(mosq_, nullptr, topic.c_str(), static_cast<int>(payload.size()),
                               payload.data(), 0, false);
    if (rc != MOSQ_ERR_SUCCESS) {
        log_error(std::string("mqtt: publish failed: ") + mosquitto_strerror(rc));
        return false;
    }
    return true;
}

void MqttPublisher::stop() {
    if (!running_) {
        return;
    }
    mosquitto_disconnect(mosq_);
    mosquitto_loop_stop(mosq_, true);  // force: don't wait on a reconnect sleep
    running_ = false;
    connected_ = false;
}

void MqttPublisher::on_connect(struct mosquitto *, void *self, int rc) {
    auto *pub = static_cast<MqttPublisher *>(self);
    if (rc == 0) {
        pub->connected_ = true;
        log_info("mqtt: connected to " + pub->host_ + ":" + std::to_string(pub->port_));
    } else {
        log_error(std::string("mqtt: broker refused connection: ") + mosquitto_connack_string(rc));
    }
}

void MqttPublisher::on_disconnect(struct mosquitto *, void *self, int rc) {
    auto *pub = static_cast<MqttPublisher *>(self);
    pub->connected_ = false;
    if (rc != 0) {
        log_error("mqtt: connection lost, reconnecting");
    }
}
