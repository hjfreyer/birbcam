import io
import os.path
import datetime
import time
import pytz


import paho.mqtt.client as mqtt
from PIL import Image
from google.cloud import storage

MQTT_USER = 'birbcam'
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD')

LOCAL_TZ = pytz.timezone('US/Eastern')

SUNRISE = datetime.time(hour=5, minute=20)
SUNSET = datetime.time(hour=8, minute=30)

NIGHT_INTERVAL = datetime.timedelta(hours=1)
DAY_INTERVAL = datetime.timedelta(minutes=10)


class Processor:
    def __init__(self):
        self._current_frame = None
        self._buffer = None

    def process(self, frame, batch, data):
        if self._current_frame != frame:
            if batch == 0:
                self._current_frame = frame
                self._buffer = b''
            else:
                return None
        self._buffer += data

        if batch == -1:
            return self._buffer
        else:
            return None


def transform_image(bytes):
    f = io.BytesIO(bytes)
    img = Image.open(f)
    img = img.transpose(method=Image.ROTATE_180)
    return img


P = Processor()


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("/birbcam/photo/#")


def message_cb(bucket):
    def on_message(client, userdata, msg):
        print("received", msg.topic)
        batch = int(os.path.basename(msg.topic))
        frame = int(os.path.basename(os.path.dirname(msg.topic)))

        if img := P.process(frame, batch, msg.payload):
            img = transform_image(img)
            filename = '%s.jpg' % datetime.datetime.now()

            blob = bucket.blob(filename)
            with blob.open('wb', ignore_flush=True, content_type='image/jpeg') as f:
                img.save(f, format='jpeg')
            bucket.copy_blob(blob, bucket, 'latest.jpg')
            print('wrote', filename)

    return on_message


def waiting_period():
    now = datetime.datetime.now(tz=LOCAL_TZ)

    if (now + NIGHT_INTERVAL).time < SUNRISE or SUNSET < now.time:
        return NIGHT_INTERVAL
    else:
        return DAY_INTERVAL


def main():
    storage_client = storage.Client()
    bucket = storage_client.bucket('hjfreyer-birbcam')

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = message_cb(bucket)

    client.tls_set()
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.connect(
        "25892ce13ca54f009b10ee48603654a5.s2.eu.hivemq.cloud", 8883, 60)
    client.loop_start()

    while True:
        client.publish('/birbcam/command/snap')
        time.sleep(waiting_period().total_seconds())


if __name__ == '__main__':
    main()
