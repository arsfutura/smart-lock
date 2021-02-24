# Smart Lock

![Smart Lock](images/smart-lock-illustration.png)

Smart Lock is a face recognition door lock we built and installed in [Ars Futura](https://arsfutura.com) office. 
It consists of four parts: **Door API**, **Camera**, **Face Recognition API** and **Engine**. Check out the [blog post](https://medium.com/@culuma/face-recognition-smart-lock-a5adcd0d585b) for more details.  

## Door API 

Door API is a component which provides `/unlock` endpoint for unlocking the door.

This component is built for unlocking doors with [electric strike](https://en.wikipedia.org/wiki/Electric_strike). 
Doors with electric strike are controlled by applying electric current to strike which unlocks (fail-secure) or locks it
(fail-safe). For setting up Door API you need [Raspberry Pi](https://www.raspberrypi.org/) and 
[5V relay](https://www.makershop.de/en/module/relais/1-kanal-relais/). Connect Raspberry Pi to relay and connect relay 
to door electric strike circuit to relay NC (normally closed) contact. Door API is implemented as 
[Flask](https://palletsprojects.com/p/flask/) server. `/unlock` endpoint activates relay through Raspberry Pi GPIO pins, 
when relay is activated it connects door electric strike circuit which applies current to it and unlocks it 
(fail-secure case). Check out [api.py](door-api/api.py) to see full implementation.

Here's a good [tutorial](https://www.instructables.com/id/5V-Relay-Raspberry-Pi/) on how to control relay using 
Raspberry Pi, in this tutorial author uses relay NO (normally open) contact, Door API assumes NC contact, but the 
logic for controlling relay is pretty much the same. 

> WARNING: If you are working with alternating current, be extremely cautious! Don't try anything without the 
> supervision of trained professional!

Once you have all hardware setup, you can run Door API by running following commands on Raspberry Pi: 

```shell script
cd door-api
pip install -r requirements.txt
python api.py --pin GPIO_PIN_INDEX
```

or just run it with Docker in one easy step ([Docker installation](https://dev.to/rohansawant/installing-docker-and-docker-compose-on-the-raspberry-pi-in-5-simple-steps-3mgl)):

```shell script
docker run --name smart-lock-door-api --privileged --restart=always -d -p 80:80 arsfutura/smart-lock-door-api:latest --pin GPIO_PIN_INDEX
```

Once you have Door API up and running POST request to `http://DOOR_IP/unlock` should unlock the door. Door API will 
return `202` if unlock request is successfully accepted. 

`api.py --help`
```text
usage: Simple Flask api for unlocking door with electric strike lock connected with Raspberry Pi via GPIO pins.
       -p PIN [-d LOCK_DELAY] [-h]

required arguments:
  -p PIN, --pin PIN     Index of GPIO pin (in GPIO.BOARD mode) which controls
                        relay.

optional arguments:
  -d LOCK_DELAY, --lock-delay LOCK_DELAY
                        How much time should we activate relay.
  -h, --help            show this help message and exit
```

## Camera

Camera provides video stream which can be easily connected to programmatically. 

This component is built for providing video stream on top of Raspberry Pi with 
[camera module](https://www.makershop.de/en/raspberry-pi/pi-kameramodul/).

You can run Camera component by running following commands on Raspberry Pi (make sure you [configure](https://www.raspberrypi.org/documentation/configuration/camera.md) camera before using it): 
```shell script
cd camera
pip install -r requirements.txt
python stream.py
```

or just run it with Docker in one easy step ([Docker installation](https://dev.to/rohansawant/installing-docker-and-docker-compose-on-the-raspberry-pi-in-5-simple-steps-3mgl)):

```shell script
docker run --name smart-lock-camera --privileged --restart=always -d -p 80:80 arsfutura/smart-lock-camera:latest
```

Once you have Camera up and running you can access live camera stream on `http://CAMERA_IP` and `MJPG` stream on 
`http://CAMERA_IP/stream.mjpg`.

## Face Recognition API

[Face Recognition API](https://github.com/arsfutura/face-recognition#face-recognition-api) provides `/face-recognition` 
endpoint for classifying people in images. 

Check out [face-recognition](https://github.com/arsfutura/face-recognition) repository for 
instructions on how to generate Face Recognition API. Also, if your are interested in inner workings of face-recognition, 
check out this [blog post](https://arsfutura.co/magazine/face-recognition-with-facenet-and-mtcnn/) which explains it.

## Engine

Engine is a component which connects everything together and makes Smart Lock work. 

Engine connects to Camera, does classification on camera frames using Face Recognition API and unlocks the door using 
Door API if a known person is recognised on a camera frame. Actual engine algorithm is a little bit more complicated, 
check [engine.py](engine/engine.py) for details. Engine logs all actions and frames which trigger unlocks for debugging 
purposes, logs are located in user-defined folder (check `--log-path` argument). 

You can run Engine component by running following commands:
```shell script
pip install -r engine/requirements.txt
python -m engine.engine --threshold THRESHOLD --camera-url http://CAMERA_IP/stream.mjpg --face-recognition-api-url http://FACE_RECOGNITION_IP:5000/face-recognition --door-api-url http://DOOR_IP/unlock
```

or just run it with Docker in one easy step:

```shell script
docker run --name smart-lock-engine --mount source=smart-lock-logs,target=/app/log --restart=always -d arsfutura/smart-lock-engine 
            --threshold THRESHOLD 
            --camera-url http://CAMERA_IP/stream.mjpg 
            --face-recognition-api-url http://FACE_RECOGNITION_IP:5000/face-recognition 
            --door-api-url http://DOOR_IP/unlock
```

Engine depends on Camera, Door API and Face Recognition API but these 3 components don't have to be the exact ones 
described here. Camera stream can really be any video stream which is supported by OpenCV VideoCapture. Door API can be 
any HTTP POST endpoint, engine doesn't care what it does. Engine does assume that Face Recognition API is from 
[face-recognition](https://github.com/arsfutura/face-recognition) library, but again, it treats it as a HTTP POST 
endpoint, if you implement same response as Face Recognition API, you can have anything behind that endpoint. Basically, 
instead of unlocking, you could set up Engine to send you a message when some person appears in video stream.

`engine.py --help`
```text
usage: engine.py --camera-url CAMERA_URL --face-recognition-api-url
                 FACE_RECOGNITION_API_URL --door-api-url DOOR_API_URL
                 --threshold THRESHOLD [--fps FPS]
                 [--haar-file-path HAAR_FILE_PATH] [--log-path LOG_PATH]
                 [--block-time BLOCK_TIME] [-h]

Face recognition engine which hooks to camera stream, performs face
recognition on stream frames and sends unlocks door request if a familiar face
is recognised.

required arguments:
  --camera-url CAMERA_URL
                        URL of video stream.
  --face-recognition-api-url FACE_RECOGNITION_API_URL
                        URL of face recognition endpoint.
  --door-api-url DOOR_API_URL
                        URL of smart lock door-api which unlocks door.
  --threshold THRESHOLD
                        Number from 0 to 1 which represents minimal confidence
                        which need to be met to unlock the door when face is
                        recognised from a video stream. Default values is 0.8
                        (We need to be at least 80% sure that we recognised
                        some person to unlock the door for him).

optional arguments:
  --fps FPS             How many frames per second will engine be processing.
                        This parameter affects engine performance the most,
                        setting too high fps can dramatically slow down the
                        engine. Default value od 2 should be good enough in
                        most situations.
  --haar-file-path HAAR_FILE_PATH
                        Path to Haar Cascade (simple and fast face detector)
                        xml file.
  --log-path LOG_PATH   Directory path where logs will be saved. Default is
                        "log".
  --block-time BLOCK_TIME
                        After door is unlocked engine will stop processing
                        frame for block-time seconds. By default, engine will
                        stop processing frames for 6 seconds after unlock.
  -h, --help            show this help message and exit
```

## Data collector

Data collector is convenience component for collecting data. It logs every frame which recognises a person where 
`min_confidence <= person_confidence <= max_confidence`. 

This component was built for collecting additional data in cases where Face Recognition API doesn't assign high-enough 
confidence to people. Let's say you set your Engine threshold to 0.8 (80%) and there are some people who consistently 
get assigned confidences in range of 60%-80%, rarely enough to break the threshold and get door unlocked, this means 
that you lack data for those people (issue could also be that you underfitted or overfitted your model, but let's 
assume that's not the case here). In order to gather more data, you run data collector with min confidence of 0.6 and 
max confidence of 0.8, collect those frames that you need (manually choose frames that are good, don't take blurry 
frames or ones where person is not front facing the camera) and retrain your model, this should boost your model 
performance.   

You can run Data collector by running following commands:
```shell script
pip install -r data-collector/requirements.txt
python -m data-collector.collector -min MIN_CONFIDENCE -max MAX_CONFIDENCE --camera-url http://CAMERA_IP/stream.mjpg --face-recognition-api-url http://FACE_RECOGNITION_IP:5000/face-recognition
```

or just run it with Docker in one easy step:

```shell script
docker run --name smart-lock-data-collector --mount source=data,target=/app/log --restart=always -d arsfutura/smart-lock-data-collector 
            -min MIN_CONFIDENCE
            -max MAX_CONFIDENCE
            --camera-url http://CAMERA_IP/stream.mjpg 
            --face-recognition-api-url http://FACE_RECOGNITION_IP:5000/face-recognition 
```

Little tip for Docker Mac users, run following command to backup volumes from Docker VM to host machine:
```shell script
docker run --rm -it -v /path/to/folder/on/your/mac:/backup -v /var/lib/docker:/docker alpine:edge tar cfz /backup/volumes.tgz /docker/volumes/
``` 
Now you have backup of Docker volumes in `/path/to/folder/on/your/mac`. 
