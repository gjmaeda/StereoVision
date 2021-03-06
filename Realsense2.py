import cv2 as cv
import numpy as np
from matplotlib import pyplot as plt
import time
# import orbslam2
from scipy.signal import butter, lfilter, filtfilt
import pyrealsense2 as rs
import math

class Realsense:

    def __init__(self):
        # Define the paramateres for the disparity map, the calibration rectification
        # and other values

        self.h, self.w = 480, 640
        self.slam = []
        self.out = []
        self.f = []
        self.pipeline = []
        self.point_3d = []
        self.point2_3d = []
        self.goal_3d = []
        self.align = []
        self.hsv = []
        # Filter requirements.
        self.order = 3
        self.fs = 60.0  # sample rate, Hz
        self.cutoff = 2.  # desired cutoff frequency of the filter, Hz

    def butter_lowpass(self):
        nyq = 0.5 * self.fs
        normal_cutoff = self.cutoff / nyq
        b, a = butter(self.order, normal_cutoff, btype='low', analog=False)
        return b, a

    def butter_lowpass_filter(self, data):
        b, a = self.butter_lowpass()
        # y = lfilter(b, a, data)
        y = filtfilt(b, a, data, padlen=50)
        return y

    def Initialize_Realsense(self, slam_bool=False, file_capture=False):
        # Configure depth and color streams
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.depth, self.w, self.h, rs.format.z16,  60)
        config.enable_stream(rs.stream.color, self.w, self.h, rs.format.bgr8, 60)

        # Start streaming
        self.pipeline.start(config)

        align_to = rs.stream.color
        self.align = rs.align(align_to)

        if slam_bool:
            vocab_path = "Parameters/ORBvoc.txt"
            settings_path = "Parameters/Realsense.yaml"
            self.slam = orbslam2.System(vocab_path, settings_path, orbslam2.Sensor.RGBD)
            self.slam.set_use_viewer(True)
            self.slam.initialize()

        if file_capture:
            self.f = open("Data.txt", "w+")

    def detect_ball(self, image, show=False):
        # Part of the code to track the ball

        self.hsv = cv.cvtColor(image, cv.COLOR_BGR2HSV)
        mask = cv.inRange(self.hsv, (0, 100, 20), (20, 255, 255))
        mask = cv.erode(mask, None, iterations=1)
        mask = cv.dilate(mask, None, iterations=3)
        cnts = cv.findContours(mask.copy(), cv.RETR_EXTERNAL,
                               cv.CHAIN_APPROX_SIMPLE)[-2]

        x, xc = 0, 0
        y, yc = 0, 0
        radius = 0
        # only proceed if at least one contour was found
        if len(cnts) > 0:
            # find the largest contour in the mask, then use
            # it to compute the minimum enclosing circle and
            # centroid
            c = max(cnts, key=cv.contourArea)
            ((x, y), radius) = cv.minEnclosingCircle(c)

            # only proceed if the radius meets a minimum size
            if radius > 10:
                # computing the centroid of the ball
                M = cv.moments(c)
                center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                # draw the circle and centroid on the frame,
                # then update the list of tracked points
                cv.circle(image, (int(x), int(y)), int(radius), (0, 255, 255), 1)
                cv.circle(image, center, 2, (0, 255, 255), -1)

                xc = int(x)
                yc = int(y)

        if show:
            cv.imshow('Image_', mask)
            cv.moveWindow('Image_', 100, 200)

        return xc, yc, int(radius)

    def detect_goal(self, image, show=False):
        # Part of the code to track the goal
        mask_g = cv.inRange(self.hsv, (40, 100, 40), (90, 255, 255))
        mask_g = cv.erode(mask_g, None, iterations=1)
        mask_g = cv.dilate(mask_g, None, iterations=3)
        cnts = cv.findContours(mask_g.copy(), cv.RETR_EXTERNAL,
                               cv.CHAIN_APPROX_SIMPLE)[-2]

        x, xc = 0, 0
        y, yc = 0, 0
        radius = 0
        # only proceed if at least one contour was found
        if len(cnts) > 0:
            # find the largest contour in the mask, then use
            # it to compute the minimum enclosing circle and
            # centroid
            c = max(cnts, key=cv.contourArea)
            ((x, y), radius) = cv.minEnclosingCircle(c)
            # only proceed if the radius meets a minimum size
            if radius > 10:
                # computing the centroid of the goal
                M = cv.moments(c)
                center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))
                # draw the circle and centroid on the frame,
                # then update the list of tracked points
                cv.circle(image, (int(x), int(y)), int(radius), (0, 255, 255), 1)
                cv.circle(image, center, 2, (0, 255, 255), -1)
                xc = int(x)
                yc = int(y)

        if show:
            cv.imshow('Image_Goal', mask_g)
            cv.moveWindow('Image_Goal', 800, 200)
        return xc, yc, int(radius)

    def transform_disp_3d(self, xc, yc, depth_frame, depth_intrin):
        depth = depth_frame.get_distance(xc, yc)
        point_3d = rs.rs2_deproject_pixel_to_point(depth_intrin, [xc, yc], depth)
        return point_3d

    def collect_single_frame_data(self, frames, start, show=False, file_capture=False):
        # This function gets the 3d coordinates of the basketball for one frame, to be called inside a loop

        # Align the depth frame to color frame
        aligned_frames = self.align.process(frames)
        # Get aligned frames
        depth_frame = aligned_frames.get_depth_frame()  # aligned_depth_frame is a 640x480 depth image
        color_frame = aligned_frames.first(rs.stream.color)

        # Convert images to numpy arrays
        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        # Intrinsics & Extrinsics
        depth_intrin = depth_frame.profile.as_video_stream_profile().intrinsics

        # Apply colormap on depth image (image must be converted to 8-bit per pixel first)
        depth_colormap = cv.applyColorMap(cv.convertScaleAbs(depth_image, alpha=0.03), cv.COLORMAP_JET)
        xc, yc, _ = self.detect_ball(color_image, show)
        xg, yg, _ = self.detect_goal(color_image, show)

        # Transform these 2d coordinates into 3d
        self.point_3d = self.transform_disp_3d(xc, yc, depth_frame, depth_intrin)
        self.point2_3d = self.transform_disp_3d(xg, yg, depth_frame, depth_intrin)

        # if we want to save the values in a file
        if file_capture:
            self.f.write("{}, {}, {}, {} \n".format(self.point_3d[0], self.point_3d[1],
                                                    self.point_3d[2]))

        if self.point2_3d:
            self.goal_3d.append([self.point2_3d[0], self.point2_3d[1], self.point2_3d[2]])

        if self.point_3d:
            self.out.append([self.point_3d[0], self.point_3d[1], self.point_3d[2]])

        if show:
            # Stack both images horizontally
            images = np.hstack((color_image, depth_colormap))
            cv.imshow('RealSense',images)

    def collect_frames_data(self, num_frames, show=False, file_capture=False):
        # This part of the code give you the matrix of 3d coordinates of the ball for X frames

        # Start by initializing the mapping and disparity
        self.Initialize_Realsense()

        # Start a counter to measure fps
        start = time.time()

        for frame in range(num_frames):
            # Wait for a coherent pair of frames: depth and color
            frames = self.pipeline.wait_for_frames()
            if frame > 50:
                self.collect_single_frame_data(frames, start, show, file_capture)
            if cv.waitKey(1) & 0xFF == ord('q'):
                break

        # End time
        end = time.time()

        # Time elapsed
        seconds = end - start
        print("Time taken : {0} seconds".format(seconds))

        # Calculate frames per second
        fps = num_frames / seconds
        print("Estimated frames per second : {0}".format(fps))

        return self.out

    def plot_charts(self):
        # Funtion to plot the 3d coordinates
        self.out = np.array(self.out)
        self.goal_3d = np.array(self.goal_3d)
        # plt.figure('time')
        # plt.plot(self.out[:, 0], label='3D')
        # plt.legend(loc='upper left')
        plt.figure('x cm')
        #y1 = self.butter_lowpass_filter(self.out[:, 1])
        plt.plot(self.out[:, 0]*100, label='3D')
        plt.plot(self.goal_3d[:, 0]*100, label='3D_goal')
        #plt.plot(y1, label='3D filtered')
        plt.legend(loc='upper left')
        plt.figure('y cm')
        #y2 = self.butter_lowpass_filter(self.out[:, 2])
        plt.plot(self.out[:, 1]*100, label='3D')
        plt.plot(self.goal_3d[:, 1]*100, label='3D_goal')
        #plt.plot(y2, label='3D filtered')
        plt.legend(loc='upper left')
        plt.figure('z cm')
        #y3 = self.butter_lowpass_filter(self.out[:, 3])
        plt.plot(self.out[:, 2]*100, label='3D')
        plt.plot(self.goal_3d[:, 2]*100, label='3D_goal')
        #plt.plot(y3, label='3D filtered')
        plt.legend(loc='upper left')
        plt.show()

    def destroy_feed(self, file_capture=False):
        # release the cameras and destroy the windows opened
        if file_capture:
            self.f.close()

        cv.destroyAllWindows()
        self.pipeline.stop()

    def save_trajectory(self, filename):
        with open(filename, 'w') as traj_file:
            traj_file.writelines(
                ' TIME {time} {r00} {r01} {r02} {t0} {r10} {r11} {r12} {t1} {r20} {r21} {r22} {t2}\n'.format(
                    time=repr(t),
                    r00=repr(r00),
                    r01=repr(r01),
                    r02=repr(r02),
                    t0=repr(t0),
                    r10=repr(r10),
                    r11=repr(r11),
                    r12=repr(r12),
                    t1=repr(t1),
                    r20=repr(r20),
                    r21=repr(r21),
                    r22=repr(r22),
                    t2=repr(t2)
                ) for t, r00, r01, r02, t0, r10, r11, r12, t1, r20, r21, r22, t2 in self.slam.get_trajectory_points())

    def save_keyframe(self, filename):
        with open(filename, 'w') as traj_file:
            traj_file.writelines(
                ' TIME {time} {r00} {r01} {r02} {t0} {r10} {r11} {r12} {t1} {r20} {r21} {r22} {t2}\n'.format(
                    time=repr(t),
                    r00=repr(r00),
                    r01=repr(r01),
                    r02=repr(r02),
                    t0=repr(t0),
                    r10=repr(r10),
                    r11=repr(r11),
                    r12=repr(r12),
                    t1=repr(t1),
                    r20=repr(r20),
                    r21=repr(r21),
                    r22=repr(r22),
                    t2=repr(t2)
                ) for t, r00, r01, r02, t0, r10, r11, r12, t1, r20, r21, r22, t2 in self.slam.get_keyframe_points())

    def SLAM_single_cycle(self, frames, start, show = False):
        t = time.time()
        seconds = t - start
        tframe = seconds

        # Align the depth frame to color frame
        aligned_frames = self.align.process(frames)
        # Get aligned frames
        depth_frame = aligned_frames.get_depth_frame()  # aligned_depth_frame is a 640x480 depth image
        color_frame = aligned_frames.first(rs.stream.color)

        # Convert images to numpy arrays
        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        # Intrinsics & Extrinsics
        depth_intrin = depth_frame.profile.as_video_stream_profile().intrinsics

        xc, yc, _ = self.detect_ball(color_image, show)
        xg, yg, _ = self.detect_goal(color_image, show)

        # Transform these 2d coordinates into 3d
        self.point_3d = self.transform_disp_3d(xc, yc, depth_frame, depth_intrin)
        self.point2_3d = self.transform_disp_3d(xg, yg, depth_frame, depth_intrin)

        if self.point2_3d:
            self.goal_3d.append([self.point2_3d[0], self.point2_3d[1], self.point2_3d[2]])

        if self.point_3d:
            self.out.append([self.point_3d[0], self.point_3d[1], self.point_3d[2]])

        if show:
            depth_colormap = cv.applyColorMap(cv.convertScaleAbs(depth_image, alpha=0.03), cv.COLORMAP_JET)
            # Stack both images horizontally
            images = np.hstack((color_image, depth_colormap))
            cv.imshow('RealSense',images)

        t1 = time.time()
        self.slam.process_image_rgbd(color_image, depth_image, tframe)
        t2 = time.time()

        ttrack = t2 - t1
        return ttrack

    def SLAM(self, num_frames, show = False):

        # Start by initializing the mapping and disparity
        self.Initialize_Realsense(slam_bool=True)

        # Start a counter to measure fps
        start = time.time()

        times_track = [0 for _ in range(num_frames)]
        print('-----')
        print('Start processing sequence ...')
        glob_XX = []
        glob_YY = []
        glob_ZZ = []
        glob_GX = []
        glob_GY = []
        glob_GZ = []

        for idx in range(num_frames):
            frames = self.pipeline.wait_for_frames()
            # Wait for a coherent pair of frames: depth and color
            if idx>50:
                times_track[idx] = self.SLAM_single_cycle(frames, start, show)
                current_traj = self.slam.get_trajectory_points()
                out = np.array(self.out)
                goal = np.array(self.goal_3d)
                current_traj = np.array(current_traj)

                glob_XX.append((out[-1, 0]*current_traj[-1, 1]) + (out[-1, 1]*current_traj[-1, 2])
                              + (out[-1, 2]*current_traj[-1,3]) + current_traj[-1,4])
                glob_YY.append((out[-1, 0]*current_traj[-1, 5]) + (out[-1, 1]*current_traj[-1, 6])
                              + (out[-1, 2]*current_traj[-1,7]) + current_traj[-1,8])
                glob_ZZ.append((out[-1, 0]*current_traj[-1, 9]) + (out[-1, 1]*current_traj[-1, 10])
                              + (out[-1, 2]*current_traj[-1,11]) + current_traj[-1,12])

                glob_GX.append((goal[-1, 0]*current_traj[-1, 1]) + (goal[-1, 1]*current_traj[-1, 2])
                              + (goal[-1, 2]*current_traj[-1,3]) + current_traj[-1,4])
                glob_GY.append((goal[-1, 0]*current_traj[-1, 5]) + (goal[-1, 1]*current_traj[-1, 6])
                              + (goal[-1, 2]*current_traj[-1,7]) + current_traj[-1,8])
                glob_GZ.append((goal[-1, 0]*current_traj[-1, 9]) + (goal[-1, 1]*current_traj[-1, 10])
                              + (goal[-1, 2]*current_traj[-1,11]) + current_traj[-1,12])
            if cv.waitKey(1) & 0xFF == ord('q'):
                break

        # End time
        end = time.time()
        # Time elapsed
        seconds = end - start
        print("Time taken : {0} seconds".format(seconds))

        # Calculate frames per second
        fps = num_frames / seconds
        print("Estimated frames per second : {0}".format(fps))

        self.save_trajectory('trajectory.txt')
        # self.save_keyframe('keyframe.txt')

        trajec = self.slam.get_trajectory_points()
        trajec = np.array(trajec)

        self.out = np.array(self.out)

        glob_X = np.array(glob_XX)
        glob_Y = np.array(glob_YY)
        glob_Z = np.array(glob_ZZ)
        glob_GX = np.array(glob_GX)
        glob_GY = np.array(glob_GY)
        glob_GZ = np.array(glob_GZ)

        self.slam.shutdown()
        plt.figure('slam')
        plt.plot(trajec[:, 4], trajec[:, 12], 'b', label='Stereo system')
        plt.plot(glob_X, glob_Z, 'g', label='3D global', marker='*')
        plt.plot(glob_GX, glob_GZ, 'r', label='3D goal', marker='*')
        #plt.legend(loc=2)

        times_track = sorted(times_track)
        total_time = sum(times_track)
        print('-----')
        print('median tracking time: {0}'.format(times_track[num_frames // 2]))
        print('mean tracking time: {0}'.format(total_time / num_frames))
        plt.show()

        return 0


if __name__ == '__main__':
    # Here is an example of how to run the code to get the coordinates
    num_frames = 600
    disparity_map = Realsense()
    out = disparity_map.collect_frames_data(num_frames, show=False)
    #disparity_map.SLAM(num_frames, show=False)
    #disparity_map.destroy_feed()
    #disparity_map.plot_charts()
