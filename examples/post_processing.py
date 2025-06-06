# ******************************************************************************
#  Copyright (c) 2024 Orbbec 3D Technology, Inc
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http:# www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# ******************************************************************************
import sys

import cv2
import numpy as np

from pyorbbecsdk import *

ESC_KEY = 27
PRINT_INTERVAL = 1  # seconds
MIN_DEPTH = 20  # 20mm
MAX_DEPTH = 10000  # 10000mm

def main():
    pipeline = Pipeline()
    config = Config()
    try:
        profile_list = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
        depth_profile = profile_list.get_default_video_stream_profile()
        config.enable_stream(depth_profile)
    except Exception as e:
        print(e)
        return

    try:
        pipeline.enable_frame_sync()
    except Exception as e:
        print(e)

    try:
        pipeline.start(config)
    except Exception as e:
        print(e)
        return

    device = pipeline.get_device()
    assert device is not None
    depth_sensor = device.get_sensor(OBSensorType.DEPTH_SENSOR)
    assert depth_sensor is not None
    filter_list = depth_sensor.get_recommended_filters()
    assert filter_list is not None
    # print filter list
    for i in range(len(filter_list)):
        post_filter = filter_list[i]
        if post_filter:
            print("filter name: ", post_filter.get_name())
            print("filter is enabled: ", post_filter.is_enabled())

    while True:
        try:
            frames = pipeline.wait_for_frames(100)
            if not frames:
                continue
            depth_frame = frames.get_depth_frame()
            if not depth_frame:
                continue
            for i in range(len(filter_list)):
                post_filter = filter_list[i]
                if post_filter and post_filter.is_enabled() and depth_frame:
                    depth_data_size = depth_frame.get_data()
                    if len(depth_data_size) < (depth_frame.get_width() * depth_frame.get_height() * 2):
                        # print("depth data is not complete")
                        continue

                    new_depth_frame = post_filter.process(depth_frame)
                    depth_frame = new_depth_frame.as_depth_frame()
            # for Y16 format depth frame, print the distance of the center pixel every 30 frames
            width = depth_frame.get_width()
            height = depth_frame.get_height()
            scale = depth_frame.get_depth_scale()
            depth_format = depth_frame.get_format()
            if depth_format != OBFormat.Y16:
                print("depth format is not Y16")
                continue
            try:
                depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16)
                depth_data = depth_data.reshape((height, width))
            except ValueError:
                print("Failed to reshape depth data")
                continue

            depth_data = depth_data.astype(np.float32) * scale
            depth_data = np.where((depth_data > MIN_DEPTH) & (depth_data < MAX_DEPTH), depth_data, 0)
            depth_data = depth_data.astype(np.uint16)
            if depth_frame.get_format() == OBFormat.Y16 and depth_frame.get_index() % 30 == 0:
                # print the distance of the center pixel
                center_y = int(height / 2)
                center_x = int(width / 2)
                center_distance = depth_data[center_y, center_x]
                print("center distance: ", center_distance)
            depth_image = cv2.normalize(depth_data, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            depth_image = cv2.applyColorMap(depth_image, cv2.COLORMAP_JET)

            cv2.imshow("Depth Viewer", depth_image)
            key = cv2.waitKey(1)
            if key == ord('q') or key == ESC_KEY:
                break
        except KeyboardInterrupt:
            break
    cv2.destroyAllWindows()
    pipeline.stop()


if __name__ == "__main__":
    main()
