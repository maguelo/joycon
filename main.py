import time
from joycon import Joycon


if __name__ == '__main__':

    joycon_left, joycon_right = Joycon.discover()

    joycon_left.connect()
    joycon_right.connect()

    joycon_left.calibrate()
    joycon_right.calibrate()

    print(joycon_left.status())
    print(joycon_right.status())

    lamp_pattern = 0
    iteration = 0
    
    while iteration<100:
        print("left",joycon_left.get_status())
        print("right",joycon_right.get_status())
    
        joycon_left.set_player_lamp_on(lamp_pattern)
        joycon_right.set_player_lamp_on(lamp_pattern)
    
        lamp_pattern = (lamp_pattern + 1) & 0xf
    
        time.sleep(0.1)
    
        iteration+=1

    joycon_left.disconnect()
    joycon_right.disconnect()
    