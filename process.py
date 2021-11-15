from __future__ import print_function
import subprocess
import datetime
import argparse
import os
import shutil
import timeit
import time
import fd
import upload
import freezedetect
import gc
import signal
import sys
import requests
import xml.etree.ElementTree as ET
import pandas as pd


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def signal_handler(signal, frame):
    gc.collect()
    sys.exit(0)

def sign(x):
    if x > 0:
        return 1
    if x < 0:
        return -1
    if x == 0:
        return 0

class Process:
    def __init__(self, dir, out_gpx, out_vid, sens, noise, file, gpx, sheet, route, batch):
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        self.directory = dir
        self.output_gpx = self.script_dir + "/" + out_gpx
        self.output_vid = self.script_dir + "/" + out_vid
        self.gpx = gpx
        self.sheet = sheet
        self.sensitivity = sens
        self.noise = noise
        self.file = file
        self.people = 0
        self.batch = batch
        self.route = route
        self.stats_url = 'http://18.136.217.164:3001/process/tracking/stats'
        self.tracking_url = 'http://18.136.217.164:3001/process/tracking'
        self.speed_bool = True

    def start(self):
        self.generate_receipt()
        start = timeit.default_timer()
        stats = {}
        listdir = os.listdir(self.directory)
        filename = ''
        if (self.file == ''):
            concat_gps_track = self.concat_gps_track(listdir)
            if (self.gpx != ''):
                dict_arr = self.parse_GPX_to_dict(self.gpx)
            else:
                dict_arr = self.gps_dict_arr(concat_gps_track)
                dict_arr2 = self.gps_dict_arr2(concat_gps_track)

            print(self.gpx, dict_arr)

            #self.create_gpx(dict_arr)
            for i in listdir:
                #self.tracking('Processing', i)
                break
            print('[-] Concatenating...')
            self.quick_concat(listdir)
        else:
            filename = self.file.split('/')[-1]
            stats['filename'] = filename
            stats['duration'] = self.get_duration(self.file)
            if (self.gpx != ''):
                dict_arr = self.parse_GPX_to_dict(self.gpx)
            elif (self.sheet != ''):
                dict_arr = self.parse_sheet_to_dict(self.sheet)
            else:
                gps_track = self.get_gps_track(self.file)
                dict_arr = self.gps_dict_arr(gps_track)
                dict_arr2 = self.gps_dict_arr(gps_track)
            #self.create_gpx(dict_arr)

            self.output_vid = self.file
            #self.tracking('Processing', filename)

        print('[-] Getting stops...')
        if (self.speed_bool):
            print('\t by speed')
            stops1, t_speed = self.clean_stops(self.stops_by_speed(dict_arr))
        else:
            print('\t by location')
            stops1, t_speed = self.clean_stops(self.stops_by_location(dict_arr))

        # Adding 1 to timeframe
        start_t = self.get_datetime(dict_arr[0]["date/time"])
        end_t = self.get_datetime(dict_arr[-1]["date/time"])
        duration = (end_t - start_t).seconds
        self.add_to_timeframe(stops1, duration)

        # print('--- STOPS BY SPEED ---')
        # stops2, t_loc = self.stops_by_location(dict_arr)
        # print('--- STOPS BY LOCATION ---')
        # for i in stops2:
        #     print(i)
        # stops3, t_freezedetect = self.clean_stops(self.stops_by_freezedetect(self.freezedetect(self.output_vid, self.sensitivity, self.noise)))
        # print('--- STOPS BY FREEZEDETECT ---')
        # for i in stops3:
        #     print(i)
        print('[-] Splicing...')
        stops1 = self.splice2(self.script_dir + "/speed", stops1)
        # self.splice("location", stops2)
        # self.splice("freezedetect", stops3)
        print(stops1)
        
        print('[-] Screening stops')
        screener = freezedetect.Screener(stops=stops1)
        stops1, for_deletion = screener.screen()


        print('[-] Aggregating and sending stats')

        stats['splices'] = len(stops1)
        resulting = 0
        for i in stops1:
            stop_dur = self.get_duration(self.script_dir + "/speed/{}".format(i["file"]))
            i["duration"] = stop_dur
            resulting += stop_dur

        stats['resulting'] = resulting
        
        self.send_stats(stats)

        print('[-] Counting...')
        if (self.file == ''):
            for i in listdir:
                break
                #self.tracking('CV Processing', i)
        #else:
            #self.tracking('CV Processing', filename)

        for i in range(len(stops1)):
            # if (self.file == ''):
            #     for j in listdir:
            #         break
            #         self.tracking('CV Processing - Splice: {} - {} / {}'.format(stops1[i]["file"], i, len(stops1)), j)
            # else:
            #     break
            #     self.tracking('CV Processing - Splice {} out of {}'.format(i + 1, len(stops1) + 1), filename)
            video = "{}/{}".format(self.script_dir + "/speed", stops1[i]["file"])
            fd_instance = fd.FaceDetect(video=video, weight=self.script_dir + "/model.pkl", detect_interval=8, sleep_interval=0, play=False)
            fd_instance.run()
            stops1[i]["people"] = fd_instance.max
            gc.collect()

        
        if (self.file == ''):
            for i in listdir:
                break
                #self.tracking('Sending data', i)
        #else:
            #self.tracking('Sending data', filename)

        print(stops1)

        for i in stops1:
            upload.upload(self.script_dir + "/speed/{}".format(i["file"]))
            upload.insert(i["loc"][0], i["loc"][1], i["people"], i["file"], i["duration"], self.route, self.batch, (self.file.split('/'))[-1])

        if (self.file == ''):
            for i in listdir:
                break
                #self.tracking('Done!', i)
        #else:
            #self.tracking('Done!', filename)

        stop = timeit.default_timer()
        print('[-] Done! Total time elapsed: {}s'.format(stop - start))
        print('\t Stops by speed time: {}s'.format(t_speed))
        # print('\t Stops by location time: {}s'.format(t_loc))
        # print('\t Stops by freezedetect time: {}s'.format(t_freezedetect))

    def add_to_timeframe(self, stops, duration):
        for i in stops:
            stop_frame = i["stop"].split(" ")
            frame_start, frame_end = int(stop_frame[0]), int(stop_frame[1])
            if (frame_start > 0):
                frame_start += -1
            if (frame_end < duration):
                frame_end += 1

            new_frame = str(frame_start) + " " + str(frame_end)

            i["stop"] = new_frame
            

    def parse_GPX_to_dict(self, file):
        tree = ET.parse(file)
        root = tree.getroot()

        # track_seg = root[0][0] - correct for past GPX files
        # track_seg = root[0][1] - correct for Sir Richmond GPX

        track_seg = root.find('{http://www.topografix.com/GPX/1/0}trk').find('{http://www.topografix.com/GPX/1/0}trkseg') # getting the track segment element in general

        dict_arr = []

        for track_point in track_seg:
            curr_dict = {}
            curr_dict['latitude'] = track_point.attrib['lat']
            curr_dict['longitude'] = track_point.attrib['lon']
            for child in track_point:
                if (child.tag == '{http://www.topografix.com/GPX/1/0}ele'):
                    curr_dict['altitude'] = child.text
                if (child.tag == '{http://www.topografix.com/GPX/1/0}time'):
                    curr_dict['date/time'] = child.text
                if (child.tag == '{http://www.topografix.com/GPX/1/0}speed'):
                    curr_dict['speed'] = child.text

            if ('speed' not in curr_dict):
                self.speed_bool = False
            dict_arr.append(curr_dict)

        return dict_arr

    def parse_sheet_to_dict(self, file):
        sheet_ext = file.split('.')[-1].lower()
        if (sheet_ext == 'csv'):
            read_file = pd.read_csv(file)
        if (sheet_ext == 'xls' or sheet_ext == 'xlsx'):
            read_file = pd.read_excel(file)
        
        df = pd.DataFrame(read_file)

        dict_arr = []

        for i in range(df.shape[0]):
            curr_dict = {}
            curr_dict['latitude'] = df['Lat'][i]
            curr_dict['longitude'] = df['Lng'][i]

            # handling time data and checking for headers
            if 'Time' in df:
                curr_dict['date/time'] = df['Time'][i]
            else:
                curr_dict['date/time'] = df['Receive Time'][i]

            if 'Alt' in df:
                curr_dict['altitude'] = df['Alt'][i]

            if 'Speed' in df:
                curr_dict['speed'] = df['Speed'][i]
            else:
                self.speed_bool = False

            dict_arr.append(curr_dict)

        return dict_arr


    def send_stats(self, req):
        r = requests.post(self.stats_url, json=req)
        return r

    def tracking(self, status, filename):
        tracking_dict = {
            'stage': 'update',
            'status': status,
            'fileName': filename
        }
        r = requests.post(self.tracking_url, tracking_dict)
        return r

    def generate_receipt(self):
        dir = self.script_dir + "/receipt.txt"
        with open(dir, "a") as f:
            f.write("Date generated: {}\n File processed: {}\n Ran > process.py < through Anaconda Environment.Route: {}\n".format(datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"), self.file, self.route))
            f.close()

    def stop_sens(self, stop, sensitivity):
        start, end = stop.split(" ")
        if (int(end) - int(start) < sensitivity):
            return False
        else:
            return True
    
    def clean_stops(self, res):
        # print('loc: ', res)
        stops, time = res
        new_stops = []
        prev_end = -1 * self.sensitivity
        for i in stops:
            start, end = i["stop"].split(" ")
            start, end = int(start), int(end)
            if start - prev_end < self.sensitivity:
                prev_stop = new_stops.pop()
                prev_start, prev_end = prev_stop["stop"].split(" ")
                new_stop_frame = "{} {}".format(prev_start, end)
                prev_stop["stop"] = new_stop_frame
                new_stops.append(prev_stop)
            else:
                new_stops.append(i)
            prev_end = end
        return new_stops, time

    def exiftool_call(self, file):
        exif_command = "exiftool -ee {}".format(file)
        try:
            res = subprocess.check_output(exif_command, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            res = e.output
        return res

    def quick_concat(self, listdir):
        l = sorted(listdir)
        cl_comm = "("
        l.reverse()
        print(l)
        for i in range(len(l)):
            if (i != len(l) - 1):
                cl_comm += "echo file \'{}/{}\' &".format(self.directory, l[i])
            else:
                cl_comm += "echo file \'{}/{}\') > {}/list.txt".format(self.directory, l[i], self.script_dir)
        try:
            res = subprocess.check_output(cl_comm, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            res = e.output

        concat_command = "ffmpeg -y -f concat -safe 0 -i {}/list.txt -c copy {}".format(self.script_dir, self.output_vid)

        try:
            res = subprocess.check_output(concat_command, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            res = e.output

    def get_duration(self, vid):
        dur_comm = "ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {}".format(vid)
        try:
            res = subprocess.check_output(dur_comm, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            res = e.output
            return 0

        return float(res)

    def splice(self, method, stops):
        if os.path.exists(method):
            shutil.rmtree(method)
        os.makedirs(method)
        for i in range(len(stops)):
            start, end = stops[i].split(" ")
            trim_res = self.quick_trim(self.output_vid, "{}/output-{}.mov".format(method, str(i + 1)), start, end)

    def splice2(self, method, stops):
        temp_stops = stops
        if os.path.exists(method):
            shutil.rmtree(method)
        os.makedirs(method)
        for i in range(len(stops)):
            start, end = stops[i]["stop"].split(" ")
            now = datetime.datetime.now()
            string = "{}{}{}{}{}{}{}".format(now.year, now.month, now.day, now.hour, now.minute, now.second, now.microsecond)
            filename = "{}-{}.mp4".format(string, i + 1)
            trim_res = self.quick_trim(self.output_vid, "{}/{}".format(method, filename), start, end)
            temp_stops[i]["file"] = filename

        return temp_stops

    def concat_gps_track(self, listdir):
        concat_gps_track = []
        for i in sorted(listdir):
            et_out = self.exiftool_call("{}//{}".format(self.directory, i)).decode('utf-8')
            concat_gps_track += self.parse_gps_track(et_out)
        return concat_gps_track

    def get_gps_track(self, file):
        et_out = self.exiftool_call("{}".format(file)).decode('utf-8')
        gps_track = self.parse_gps_track(et_out)
        return gps_track

    def gps_dict_arr(self, gps_track_arr): # Complexity : O(TRACKPOINTS^2)
        dict_arr = []
        dict = {}
        for i in gps_track_arr:
            if (i.find("GPS Date/Time") != -1):
                if (dict.get("date/time") != None):
                    if ('speed' not in )
                    dict_arr.append(dict)
                dict = {}
                dict["date/time"] = i.split(": ")[-1]
            elif (i.find("GPS Latitude") != -1):
                deg_lat = i.split(": ")[-1]
                dict["latitude"] = self.deg_to_dec(deg_lat)
            elif (i.find("GPS Longitude") != -1):
                deg_long = i.split(": ")[-1]
                dict["longitude"] = self.deg_to_dec(deg_long)
            elif (i.find("Altitude") != -1):
                dict["altitude"] = i.split(": ")[-1]
            elif (i.find("GPS Speed Ref") != -1):
                dict["speed_ref"] = i.split(": ")[-1]
            elif (i.find("GPS Speed") != -1):
                dict["speed"] = i.split(": ")[-1]
            elif (i.find("GPS Track Ref") != -1):
                dict["track_ref"] = i.split(": ")[-1]
            elif (i.find("GPS Track") != -1):
                dict["track"] = i.split(": ")[-1]
        dict_arr.append(dict)

        return dict_arr

    def gps_dict_arr2(self, gps_track_arr): # Complexity : O(TRACKPOINTS^2)
        dict_arr = []
        dict = {}
        for i in gps_track_arr:
            if (i.find("GPS Date/Time") != -1):
                if (dict.get("date/time") != None):
                    dict_arr.append(dict)
                    if ('speed' not in dict):
                        self.speed_bool = False
                dict = {}
                dict["date/time"] = i.split(": ")[-1]
            elif (i.find("GPS Latitude") != -1):
                deg_lat = i.split(": ")[-1]
                dict["latitude"] = deg_lat
            elif (i.find("GPS Longitude") != -1):
                deg_long = i.split(": ")[-1]
                dict["longitude"] = deg_long
            elif (i.find("Altitude") != -1):
                dict["altitude"] = i.split(": ")[-1]
            elif (i.find("GPS Speed Ref") != -1):
                dict["speed_ref"] = i.split(": ")[-1]
            elif (i.find("GPS Speed") != -1):
                dict["speed"] = i.split(": ")[-1]
            elif (i.find("GPS Track Ref") != -1):
                dict["track_ref"] = i.split(": ")[-1]
            elif (i.find("GPS Track") != -1):
                dict["track"] = i.split(": ")[-1]
        dict_arr.append(dict)
        return dict_arr

    def create_gpx(self, dict_arr):
        file = open(self.output_gpx, "w")
        head = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<gpx version=\"1.0\" creator=\"ExifTool 12.06\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xmlns=\"http://www.topografix.com/GPX/1/0\" xsi:schemaLocation=\"http://www.topografix.com/GPX/1/0 http://www.topografix.com/GPX/1/0/gpx.xsd\">\n<trk>\n<trkseg>\n"
        tail = "</trkseg>\n</trk>\n</gpx>"

        body = ""
        for i in dict_arr:
            entry = "<trkpt lat=\"{}\" lon=\"{}\">\n<ele>{}</ele>\n<time>{}</time>\n<speed>{}</speed>\n</trkpt>\n".format(i["latitude"], i["longitude"], i["altitude"].strip(" m") if i.get("altitude") != None else 0, i["date/time"], i["speed"])
            body += entry

        gpx_content = head + body + tail
        file.write(gpx_content)
        file.close()

    def get_time_attr(self, datetime):
        dt_arr = datetime.split(" ")
        date = dt_arr[0]
        time = dt_arr[1].strip("Z")
        year, month, day = date.split(":")
        hour, minute, second = time.split(":")
        return int(year), int(month), int(day), int(hour), int(minute), int(second)

    def get_datetime(self, date):
        date = date.strip('Z').replace('T', ' ').replace('-', ':').split('.')[0] # unify format
        
        return datetime.datetime.strptime(date, '%Y:%m:%d %H:%M:%S')

    def process_time_frame(self, stop_start, stop_end, start_time, end_time):
        # start_year, start_month, start_day, start_hour, start_minute, start_second = self.get_time_attr(stop_start)
        # end_year, end_month, end_day, end_hour, end_minute, end_second = self.get_time_attr(stop_end)
        # begin_year, begin_month, begin_day, begin_hour, begin_minute, begin_second = self.get_time_attr(start_time)
        # final_year, final_month, final_day, final_hour, final_minute, final_second = self.get_time_attr(end_time)

        # begin_t = datetime.datetime(begin_year, begin_month, begin_day, begin_hour, begin_minute, begin_second)
        # final_t = datetime.datetime(final_year, final_month, final_day, final_hour, final_minute, final_second)
        # start_t = datetime.datetime(start_year, start_month, start_day, start_hour, start_minute, start_second)
        # end_t = datetime.datetime(end_year, end_month, end_day, end_hour, end_minute, end_second)

        # start = start_t - begin_t
        # end = end_t - begin_t
        # dur = final_t - begin_t
        # start_res = start.seconds
        # end_res = end.seconds
        # duration = dur.seconds

        # return str(start_res), str(end_res)

        # ^ Might completely deprecate get_time_attr for datetime.datetime.strptime

        begin_t2 = self.get_datetime(start_time)
        final_t2 = self.get_datetime(end_time)
        start_t2 = self.get_datetime(stop_start)
        end_t2 = self.get_datetime(stop_end)

        start2 = start_t2 - begin_t2
        end2 = end_t2 - begin_t2
        dur2 = final_t2 - begin_t2
        start_res2 = start2.seconds
        end_res2 = end2.seconds
        duration2 = dur2.seconds
        return str(start_res2), str(end_res2)


    def stops_by_speed(self, dict_arr): # Complexity : O(TRACKPOINTS)
        t_start = timeit.default_timer()
        stops = []
        stop_start = ""
        stop_end = ""
        start_time = dict_arr[0]["date/time"]
        end_time = dict_arr[-1]["date/time"]
        for i in dict_arr:
            if (float(i["speed"]) == 0.0):
                if (stop_start == ""):
                    stop_start = i["date/time"]
                    first_lat = i["latitude"]
                    first_long = i["longitude"]
                last_stop = i["date/time"]
            if ((stop_start != "") and (float(i["speed"]) != 0.0)):
                stop_end = last_stop
                rel_stop_start, rel_stop_end = self.process_time_frame(stop_start, stop_end, start_time, end_time)
                # Add a second to the start and end of the frame
                stop_frame = rel_stop_start + " " + rel_stop_end
                if (self.stop_sens(stop_frame, self.sensitivity)):
                    stop_dict = {}
                    stop_dict["loc"] = (first_lat, first_long)
                    stop_dict["stop"] = stop_frame
                    stops.append(stop_dict)
                stop_start = ""
                stop_end = ""
        if (stop_start != ""):
            rel_stop_start, rel_stop_end = self.process_time_frame(stop_start, last_stop, start_time, end_time)
            stop_frame = rel_stop_start + " " + rel_stop_end
            if (self.stop_sens(stop_frame, self.sensitivity)):
                stop_dict = {}
                stop_dict["loc"] = (first_lat, first_long)
                stop_dict["stop"] = stop_frame
                stops.append(stop_dict)
        t_end = timeit.default_timer()
        return stops, t_end - t_start

    def stops_by_location(self, dict_arr): # Complexity : O(TRACKPOINTS)
        t_start = timeit.default_timer()
        stops = []
        stop_start = ""
        stop_end = ""

        stop_loc_start_lat = dict_arr[0]["latitude"]
        stop_loc_start_long = dict_arr[0]["longitude"]

        start_time = dict_arr[0]["date/time"]
        end_time = dict_arr[-1]["date/time"]

        prev_lat = dict_arr[0]["latitude"]
        prev_long = dict_arr[0]["longitude"]

        i = 0
        #print(stop_loc_start_lat)
        #print(stop_loc_start_long)

        last_stop = ""

        for i in range(len(dict_arr)):
            stop_dict = {}

            if (dict_arr[i]['latitude'] == prev_lat and dict_arr[i]["longitude"] == prev_long):
                if (stop_start == ""):
                    if (last_stop == ""):
                        stop_start = dict_arr[i]['date/time']
                        first_lat = dict_arr[i]["latitude"]
                        first_long = dict_arr[i]["longitude"]
                    else:
                        stop_start = last_stop
            else:
                if (stop_start != ""):
                    stop_end = last_stop
                    if (stop_start != stop_end):
                        rel_stop_start, rel_stop_end = self.process_time_frame(stop_start, stop_end, start_time, end_time)
                        stop_frame = rel_stop_start + " " + rel_stop_end
                        if (self.stop_sens(stop_frame, self.sensitivity)):
                            stop_dict = {}
                            stop_dict["loc"] = (first_lat, first_long)
                            stop_dict["stop"] = stop_frame
                            stops.append(stop_dict)
                stop_start = ""
                stop_end = ""
            
            last_stop = dict_arr[i]['date/time']
            prev_lat = dict_arr[i]['latitude']
            prev_long = dict_arr[i]['longitude']

        if (stop_start != ""):
            rel_stop_start, rel_stop_end = self.process_time_frame(stop_start, last_stop, start_time, end_time)
            stop_frame = rel_stop_start + " " + rel_stop_end
            if (self.stop_sens(stop_frame, self.sensitivity)):
                stop_dict = {}
                stop_dict["loc"] = (first_lat, first_long)
                stop_dict["stop"] = stop_frame
                stops.append(stop_dict)

        # while(i < len(dict_arr)):

        #     if(dict_arr[i]["latitude"] == stop_loc_start_lat and dict_arr[i]["longitude"] == stop_loc_start_long):
        #         if (stop_start == ""):
        #             stop_start = dict_arr[i]["date/time"]
        #         last_stop = dict_arr[i]["date/time"]

        #     if(stop_start != "" and (dict_arr[i]["latitude"] != stop_loc_start_lat or dict_arr[i]["longitude"] != stop_loc_start_long)):
        #         stop_end = last_stop
        #         rel_stop_start, rel_stop_end = self.process_time_frame(stop_start, stop_end, start_time, end_time)
        #         if(rel_stop_start != rel_stop_end):
        #             stop_frame = rel_stop_start + " " + rel_stop_end
        #             if (self.stop_sens(stop_frame, self.sensitivity)):
        #                 stops.append(stop_frame)
        #         stop_start = ""
        #         stop_end = ""
                
        #     stop_loc_start_lat = dict_arr[i]["latitude"]
        #     stop_loc_start_long = dict_arr[i]["longitude"]
        #     i+=1

        t_end = timeit.default_timer()
        return stops, t_end - t_start

    def parse_gps_track(self, et_out):
        gps_track_start = et_out.find("GPS")
        gps_track_end = et_out.find("Image Size")
        gps_track = et_out[gps_track_start:gps_track_end]
        if (os.name == 'nt'):
            gps_track_arr = gps_track.split("\r\n")
        if (os.name == 'posix'):
            gps_track_arr = gps_track.split("\n")

        gps_track_arr.pop()
        return gps_track_arr

    def deg_to_dec(self, coord):
        coord_arr = coord.split(" ")
        degrees = float(coord_arr[0])
        minutes = float(coord_arr[2].strip("'"))
        seconds = float(coord_arr[3].strip("\""))
        res = sign(degrees) * (abs(degrees) + (minutes / 60) + (seconds / 3600))
        return str(res)

    def gps_track_to_json(self, gps_track_arr):
        return

    def quick_trim(self, file, output, start, end):
        trim_command = "ffmpeg -y -i {} -ss {} -to {} -c copy -an {}".format(file, start, end, output)
        try:
            res = subprocess.check_output(trim_command, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            res = e.output
        return res
    
    def freezedetect(self, file, sensitivity, noise):
        t_start = timeit.default_timer()
        command = "ffmpeg -i {} -vf \"freezedetect=n=-{}dB:d={}\" -map 0:v:0 -f null -".format(file, noise, sensitivity)
        try:
            res = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True)
        except subprocess.CalledProcessError as e:
            res = e.output
        return res.decode('utf-8'), t_start

    def get_sec(self, str):
        sec = ""

        for i in str:
            if not(i.isnumeric()):
                break
            sec += i
        return sec

    def clean(self, str):
        st = str.find("[freezedetect")
        return str[st:]

    def stops_by_freezedetect(self, tuple):
        res, t_start = tuple
        start = res.find("[freezedetect")
        list = res[start:].split("\r\n")
        for i in range(3):
            list.pop()
        
        stops = []
        stop = ""
        for i in list:
            
            parts = self.clean(i).split(" ")
            if i.find("freeze_start") != -1:
                str = parts[4]
                start = self.get_sec(str)
                #print("start: ", str)
            elif i.find("freeze_end") != -1:
                str = parts[4]
                end = self.get_sec(str)
                #print("end: ", str)
                stop = "{} {}".format(start, end)
                if (self.stop_sens(stop, self.sensitivity)):
                    stops.append(stop)
        t_end = timeit.default_timer()
        return stops, t_end - t_start

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-D', '--directory', required=False, default=os.path.dirname(os.path.realpath(__file__)) + '/data')
    parser.add_argument('-O', '--output_vid', required=False, default='output.mov')
    parser.add_argument('-G', '--gpx', required=False, default='')
    parser.add_argument('-SH', '--sheet', required=False, default='')
    parser.add_argument('-OG', '--output_gpx', required=False, default='output.gpx')
    parser.add_argument('-S', '--sensitivity', required=False, type=int, default=2)
    parser.add_argument('-N', '--noise', required=False, default=35)
    parser.add_argument('-F', '--file', required=False, default='')
    parser.add_argument('-R', '--route', required=False, default='Ikot')
    parser.add_argument('-B', '--batch', required=False, default=1)
    args = parser.parse_args()
    signal.signal(signal.SIGINT, signal_handler)
    Process(dir=args.directory, out_vid=args.output_vid, out_gpx=args.output_gpx, sens=args.sensitivity, noise=args.noise, file=args.file, gpx=args.gpx, sheet=args.sheet, route=args.route, batch=args.batch).start()
    # try:
    #     Process(dir=args.directory, out_vid=args.output_vid, out_gpx=args.output_gpx, sens=args.sensitivity, noise=args.noise, file=args.file, gpx=args.gpx, route=args.route, batch=args.batch).start()
    # except Exception as e:
    #     eprint('ERROR ENCOUNTERED: %s' % e)
        
