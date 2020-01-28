import hid
import time
import threading


class Joycon(object):
    VENDOR_ID = 1406
    PRODUCT_ID_LEFT = 8198
    PRODUCT_ID_RIGHT = 8199
    DELTA_TIME_SLEEP = 0.02

    _INPUT_REPORT_SIZE = 49
    _INPUT_REPORT_FREQ = 1.0 / 60.0
    _RUMBLE_DATA = b'\x00\x01\x40\x40\x00\x01\x40\x40'

    ACCEL_OFFSET_X = 0
    ACCEL_OFFSET_Y = 0
    ACCEL_OFFSET_Z = 0
    GYRO_OFFSET_X = 0
    GYRO_OFFSET_Y = 0
    GYRO_OFFSET_Z = 0
    STICK_OFFSET_H = 0
    STICK_OFFSET_V = 0

    def __init__(self, vendor_id, product_id):
        self.name = 'Joycon Left' if self.PRODUCT_ID_LEFT == product_id else 'Joycon Right'

        self._vendor_id = vendor_id
        self._product_id = product_id
        self._device = None
        self._status = 0

        self._stop_event = None
        self._update_input_report_thread = None
        self._input_report = bytes(self._INPUT_REPORT_SIZE)
        self._packet_number = 0

    def status(self):
        if self._status == -1:
            return "Error"
        elif self._status == 1:
            return "Connected"
        else:
            return "Not connected"

    def connect(self, sensor_calibration={}):
        self.update_sensors_calibration(sensor_calibration)
        self._open_device()
        self._setup_sensors()
        self._setup_listening_thread()

    def check_sensors_calibration(self):
        print("Calibrate START")
        steps = 30
        key = 'joycon-left' if self.is_left() else 'joycon-right'
        lamp_pattern = 0

        calibration = {'a_x': [], 'a_y': [], 'a_z': [], 'g_x': [], 'g_y': [], 'g_z': [], 's_h': [], 's_v': []}

        for step in range(steps, 0, -1):
            status = self.get_status()

            if step % 5 == 0:
                lamp_pattern = (step + 1) & 0xf
                self.set_player_lamp_on(lamp_pattern)

            calibration['a_x'].append(status[key]['accel']['x'])
            calibration['a_y'].append(status[key]['accel']['y'])
            calibration['a_z'].append(status[key]['accel']['z'])
            calibration['g_x'].append(status[key]['gyro']['x'])
            calibration['g_y'].append(status[key]['gyro']['y'])
            calibration['g_z'].append(status[key]['gyro']['z'])
            calibration['s_h'].append(status[key]['analog-sticks']['horizontal'])
            calibration['s_v'].append(status[key]['analog-sticks']['vertical'])
            time.sleep(0.1)

        calibration['a_x'] = int(sum(calibration['a_x']) / len(calibration['a_x']))
        calibration['a_y'] = int(sum(calibration['a_y']) / len(calibration['a_y']))
        calibration['a_z'] = int(sum(calibration['a_z']) / len(calibration['a_z']))

        calibration['g_x'] = int(sum(calibration['g_x']) / len(calibration['g_x']))
        calibration['g_y'] = int(sum(calibration['g_y']) / len(calibration['g_y']))
        calibration['g_z'] = int(sum(calibration['g_z']) / len(calibration['g_z']))

        calibration['s_h'] = int(sum(calibration['s_h']) / len(calibration['s_h']))
        calibration['s_v'] = int(sum(calibration['s_v']) / len(calibration['s_v']))

        print("Calibrate STOP")
        return calibration

    def update_sensors_calibration(self, sensors_calibration={}):
        self.ACCEL_OFFSET_X = sensors_calibration.get('a_x', 0)
        self.ACCEL_OFFSET_Y = sensors_calibration.get('a_y', 0)
        self.ACCEL_OFFSET_Z = sensors_calibration.get('a_z', 0)
        self.GYRO_OFFSET_X = sensors_calibration.get('g_x', 0)
        self.GYRO_OFFSET_Y = sensors_calibration.get('g_y', 0)
        self.GYRO_OFFSET_Z = sensors_calibration.get('g_z', 0)
        self.STICK_OFFSET_H = sensors_calibration.get('s_h', 0)
        self.STICK_OFFSET_V = sensors_calibration.get('s_v', 0)

    def _open_device(self):

        self._device = hid.Device(self._vendor_id, self._product_id)
        self._status = 1

    def disconnect(self):
        try:
            self._status = -1
            self._stop_listening_thread()
            time.sleep(self.DELTA_TIME_SLEEP)
            self._status = 0
        finally:
            self._device.close()
        print("Disconnect: {}".format(self.name))

    def __str__(self):
        message = 'Joycon:{{ name: {}, status: {} }}'.format(self.name, self.status())
        return message

    @staticmethod
    def discover():
        joycon_left = None
        joycon_right = None
        for device in hid.enumerate():
            if Joycon.VENDOR_ID == device['vendor_id']:
                if Joycon.PRODUCT_ID_LEFT == device['product_id']:
                    print('Joycon Left detected')
                    joycon_left = Joycon(device['vendor_id'], device['product_id'])

                elif Joycon.PRODUCT_ID_RIGHT == device['product_id']:
                    print('Joycon Right detected')
                    joycon_right = Joycon(device['vendor_id'], device['product_id'])
                else:
                    print('Unknown')
                    continue
        return joycon_left, joycon_right

    def _setup_sensors(self):
        # Enable 6 axis sensors
        self._write_output_report(b'\x01', b'\x40', b'\x01')
        # It needs delta time to update the setting
        time.sleep(self.DELTA_TIME_SLEEP)
        # Change format of input report
        self._write_output_report(b'\x01', b'\x03', b'\x30')

    def _setup_listening_thread(self):
        self._stop_event = threading.Event()
        self._update_input_report_thread = threading.Thread(target=self._update_input_report, args=(self._stop_event,))
        self._update_input_report_thread.setDaemon(True)
        self._update_input_report_thread.start()

    def _stop_listening_thread(self):
        if self._update_input_report_thread is not None:
            if self._update_input_report_thread.isAlive():
                self._stop_event.set()
                self._update_input_report_thread.join()

    def _read_input_report(self):
        return self._device.read(self._INPUT_REPORT_SIZE)

    def _write_output_report(self, command, subcommand, argument):
        self._device.write(command
                           + self._packet_number.to_bytes(1, byteorder='big')
                           + self._RUMBLE_DATA
                           + subcommand
                           + argument)
        self._packet_number = (self._packet_number + 1) & 0xF

    def _update_input_report(self, stop_event):
        print('Start listening {}'.format(self.name))
        while not stop_event.is_set():
            self._input_report = self._read_input_report()
        print('Stop listening {}'.format(self.name))

    def _to_int16le_from_2bytes(self, hbytebe, lbytebe):
        uint16le = (lbytebe << 8) | hbytebe
        int16le = uint16le if uint16le < 32768 else uint16le - 65536
        return int16le

    def _get_nbit_from_input_report(self, offset_byte, offset_bit, nbit):
        return (self._input_report[offset_byte] >> offset_bit) & ((1 << nbit) - 1)

    def is_left(self):
        return self._product_id == self.PRODUCT_ID_LEFT  # self.L_PRODUCT_ID

    def is_right(self):
        return self._product_id == self.PRODUCT_ID_RIGHT  # self.R_PRODUCT_ID

    def get_battery_charging(self):
        return self._get_nbit_from_input_report(2, 4, 1)

    def get_battery_level(self):
        return self._get_nbit_from_input_report(2, 5, 3)

    def get_button_y(self):
        return self._get_nbit_from_input_report(3, 0, 1)

    def get_button_x(self):
        return self._get_nbit_from_input_report(3, 1, 1)

    def get_button_b(self):
        return self._get_nbit_from_input_report(3, 2, 1)

    def get_button_a(self):
        return self._get_nbit_from_input_report(3, 3, 1)

    def get_button_right_sr(self):
        return self._get_nbit_from_input_report(3, 4, 1)

    def get_button_right_sl(self):
        return self._get_nbit_from_input_report(3, 5, 1)

    def get_button_r(self):
        return self._get_nbit_from_input_report(3, 6, 1)

    def get_button_zr(self):
        return self._get_nbit_from_input_report(3, 7, 1)

    def get_button_minus(self):
        return self._get_nbit_from_input_report(4, 0, 1)

    def get_button_plus(self):
        return self._get_nbit_from_input_report(4, 1, 1)

    def get_button_r_stick(self):
        return self._get_nbit_from_input_report(4, 2, 1)

    def get_button_l_stick(self):
        return self._get_nbit_from_input_report(4, 3, 1)

    def get_button_home(self):
        return self._get_nbit_from_input_report(4, 4, 1)

    def get_button_capture(self):
        return self._get_nbit_from_input_report(4, 5, 1)

    def get_button_charging_grip(self):
        return self._get_nbit_from_input_report(4, 7, 1)

    def get_button_down(self):
        return self._get_nbit_from_input_report(5, 0, 1)

    def get_button_up(self):
        return self._get_nbit_from_input_report(5, 1, 1)

    def get_button_right(self):
        return self._get_nbit_from_input_report(5, 2, 1)

    def get_button_left(self):
        return self._get_nbit_from_input_report(5, 3, 1)

    def get_button_left_sr(self):
        return self._get_nbit_from_input_report(5, 4, 1)

    def get_button_left_sl(self):
        return self._get_nbit_from_input_report(5, 5, 1)

    def get_button_l(self):
        return self._get_nbit_from_input_report(5, 6, 1)

    def get_button_zl(self):
        return self._get_nbit_from_input_report(5, 7, 1)

    def get_stick_left_horizontal(self):
        return (self._get_nbit_from_input_report(6, 0, 8) | (self._get_nbit_from_input_report(7, 0, 4) << 8)
                - self.STICK_OFFSET_H)

    def get_stick_left_vertical(self):
        return (self._get_nbit_from_input_report(7, 4, 4) | (self._get_nbit_from_input_report(8, 0, 8) << 4)
                - self.STICK_OFFSET_V)

    def get_stick_right_horizontal(self):
        return (self._get_nbit_from_input_report(9, 0, 8) | (self._get_nbit_from_input_report(10, 0, 4) << 8)
                - self.STICK_OFFSET_H)

    def get_stick_right_vertical(self):
        return (self._get_nbit_from_input_report(10, 4, 4) | (self._get_nbit_from_input_report(11, 0, 8) << 4)
                - self.STICK_OFFSET_V)

    def get_accel_x(self, sample_idx=0):
        if sample_idx not in [0, 1, 2]:
            raise IndexError('sample_idx should be between 0 and 2')
        return (self._to_int16le_from_2bytes(self._get_nbit_from_input_report(13 + sample_idx * 12, 0, 8),
                                             self._get_nbit_from_input_report(14 + sample_idx * 12, 0, 8))
                - self.ACCEL_OFFSET_X)

    def get_accel_y(self, sample_idx=0):
        if sample_idx not in [0, 1, 2]:
            raise IndexError('sample_idx should be between 0 and 2')
        return (self._to_int16le_from_2bytes(self._get_nbit_from_input_report(15 + sample_idx * 12, 0, 8),
                                             self._get_nbit_from_input_report(16 + sample_idx * 12, 0, 8))
                - self.ACCEL_OFFSET_Y)

    def get_accel_z(self, sample_idx=0):
        if sample_idx not in [0, 1, 2]:
            raise IndexError('sample_idx should be between 0 and 2')
        return (self._to_int16le_from_2bytes(self._get_nbit_from_input_report(17 + sample_idx * 12, 0, 8),
                                             self._get_nbit_from_input_report(18 + sample_idx * 12, 0, 8))
                - self.ACCEL_OFFSET_Z)

    def get_gyro_x(self, sample_idx=0):
        if sample_idx not in [0, 1, 2]:
            raise IndexError('sample_idx should be between 0 and 2')
        return (self._to_int16le_from_2bytes(self._get_nbit_from_input_report(19 + sample_idx * 12, 0, 8),
                                             self._get_nbit_from_input_report(20 + sample_idx * 12, 0, 8))
                - self.GYRO_OFFSET_X)

    def get_gyro_y(self, sample_idx=0):
        if sample_idx not in [0, 1, 2]:
            raise IndexError('sample_idx should be between 0 and 2')
        return (self._to_int16le_from_2bytes(self._get_nbit_from_input_report(21 + sample_idx * 12, 0, 8),
                                             self._get_nbit_from_input_report(22 + sample_idx * 12, 0, 8))
                - self.GYRO_OFFSET_Y)

    def get_gyro_z(self, sample_idx=0):
        if sample_idx not in [0, 1, 2]:
            raise IndexError('sample_idx should be between 0 and 2')
        return (self._to_int16le_from_2bytes(self._get_nbit_from_input_report(23 + sample_idx * 12, 0, 8),
                                             self._get_nbit_from_input_report(24 + sample_idx * 12, 0, 8))
                - self.GYRO_OFFSET_Z)

    def get_status(self):
        if self.is_left():
            return self.get_status_left()
        else:
            return self.get_status_right()

    def get_groups_event(self):
        return ["battery", "buttons", "analog-sticks", "accel", "gyro"]

    def get_status_left(self):
        return {"joycon-left": {
            "battery": {
                "charging": self.get_battery_charging(),
                "level": self.get_battery_level(),
                "charging-grip": self.get_button_charging_grip(),
            },
            "buttons": {
                "down": self.get_button_down(),
                "up": self.get_button_up(),
                "right": self.get_button_right(),
                "left": self.get_button_left(),
                "sr": self.get_button_left_sr(),
                "sl": self.get_button_left_sl(),
                "l": self.get_button_l(),
                "zl": self.get_button_zl(),
                "minus": self.get_button_minus(),
                "l-stick": self.get_button_l_stick(),
                "capture": self.get_button_capture(),
            },
            "analog-sticks": {
                "horizontal": self.get_stick_left_horizontal(),
                "vertical": self.get_stick_left_vertical(),
            },
            "accel": {
                "x": self.get_accel_x(),
                "y": self.get_accel_y(),
                "z": self.get_accel_z(),
            },
            "gyro": {
                "x": self.get_gyro_x(),
                "y": self.get_gyro_y(),
                "z": self.get_gyro_z(),
            },
        }
        }

    def get_status_right(self):
        return {"joycon-right": {
            "battery": {
                "charging": self.get_battery_charging(),
                "level": self.get_battery_level(),
                "charging-grip": self.get_button_charging_grip(),
            },
            "buttons": {
                "y": self.get_button_y(),
                "x": self.get_button_x(),
                "b": self.get_button_b(),
                "a": self.get_button_a(),
                "sr": self.get_button_right_sr(),
                "sl": self.get_button_right_sl(),
                "r": self.get_button_r(),
                "zr": self.get_button_zr(),
                "plus": self.get_button_plus(),
                "r-stick": self.get_button_r_stick(),
                "home": self.get_button_home(),
            },

            "analog-sticks": {
                "horizontal": self.get_stick_right_horizontal(),
                "vertical": self.get_stick_right_vertical(),
            },
            "accel": {
                "x": self.get_accel_x(),
                "y": self.get_accel_y(),
                "z": self.get_accel_z(),
            },
            "gyro": {
                "x": self.get_gyro_x(),
                "y": self.get_gyro_y(),
                "z": self.get_gyro_z(),
            },
        }
        }

    def set_player_lamp_on(self, on_pattern):
        self._write_output_report(b'\x01', b'\x30', (on_pattern & 0xF).to_bytes(1, byteorder='big'))

    def set_player_lamp_flashing(self, flashing_pattern):
        self._write_output_report(b'\x01', b'\x30', ((flashing_pattern & 0xF) << 4).to_bytes(1, byteorder='big'))

    def set_player_lamp(self, pattern):
        self._write_output_report(b'\x01', b'\x30', pattern.to_bytes(1, byteorder='big'))
