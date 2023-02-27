# Dynamic_RDS

A plugin for Falcon Player 6.0+ (FPP) to generate RDS (radio data system) messages similar to what is seen from typical FM stations. The RDS messages are fully customizable with static text, breaks, and grouping along with the supported data fields of title, artist, track number, track length, and main playlist item count. Currently, the plugin supportsthe QN8066 chip and there are plans to add the Si4173 in the future. The chips are controlled via the I<sup>2</sup>C bus.

## Recommended QN8066 transmitter board
```CAUTION: There are other similar looking boards, so double check for the QN8066 chip.``` For a detailed look at identifying QN8066 boards, check out [Spectraman's video](https://www.youtube.com/watch?v=i8re0nc_FdY&t=1017s).

[Aliexpress link to purchase QN8066 FM Transmitter](https://a.aliexpress.com/_mLTpVqO)

[EBay link to purchase QN8066 FM Transmitter](https://www.ebay.com/itm/275031067583?mkcid=16&mkevt=1&mkrid=711-127632-2357-0&ssspo=PB6d-PpwRGC&sssrc=2349624&ssuid=rZ11O1LCRam&var=&widget_ver=artemis&media=COPY)

![Radio Board with Screen](images/radio_board_w_screen.jpeg)
![Radio Board](images/radio_board.jpeg)

## Cable and Connectors
```CAUTION: Do not run the PWM wire along side the I<sup>2</sup>C wires.``` During testing this caused failures in the I<sup>2</sup>C commands as soon as PWM was enabled.

Pin configuration for a Raspberry Pi

![Raspberry Pi Connection](images/raspberry_pi_connection.jpeg)

Pin configuration for the Transmitter - Connector is a 5-pin JST-XH type

![Transmitter Connection](images/radio_board_pinout.jpeg)

## Using Hardware PWM on Raspberry Pi
The recommended QN8066 transmitter board can take a PWM signal to increase its power output. Be sure to comply with all applicable laws related to FM broadcasts.

```CAUTION: Do not run the PWM wire along side the I<sup>2</sup>C wires.``` During testing this caused failures in the I<sup>2</sup>C commands as soon as PWM was enabled.

On the Raspberry Pi, in order to use the hardware PWM, the built-in analog audio must be disabled and an external USB sound card is required. The built-in audio uses both hardware PWM channels to generate the audio, so PWM cannot be used for other purposes when enabled.

Modify the /boot/config.txt by by doing the following, then rebooting:
1. Comment out ```dtparm=audio=on``` with a #
   - This line may appear multiple times in the file. Comment each instance.
2. Add the line ```dtoverlay=pwm```

Don't forget to change the Audio Output Device in the FPP Settings to use the USB sound card.

## FPP After Hours Music Plugin
The Dynamic RDS Plugin has the ability to work in conjunction with the FPP After Hours Music Plugin to provide RDS Data from an internet stream of music.

Just install the After Hours Music Plugin located here:

https://github.com/jcrossbdn/fpp-after-hours

Then activate its use in Dynamic RDS Plugin.

![MPC-After-Hours](https://user-images.githubusercontent.com/23623446/201971100-7a213ef5-a22d-4e76-a545-8c8c9724a9e0.JPG)

## Troubleshooting
### Transmitter not working (for the recommended QN8066 board)
- Verify transmitter is working on it's own
   - Connect the original screen, connect antenna, and 12v power
   - Connected to audio input near the screen connector
   - Check for transmission with a radio. If not, transmitter maybe bad and need to be replaced
   - Remove power, then disconnect screen

- Verify transmitter is working with RPi/BBB
  - With everything powered off, connect the transmitter to the RPi/BBB for 3v3, GND, SDA, and SCL
  - Do NOT connect the PWM pin
  - Verify each wire is connected correctly 3v3, GND, SDA, and SCL
  - Power up the RPi/BBB
  - Transmitter will power up from power supplied by RPi/BBB (Do NOT connect 12v power yet)
  - Verify the transmitter shows up on the I<sup>2</sup>C bus at 0x21
    - Either from the Dynamic RDS config page OR
    - SSH into the RPi ```i2cdetect -y 1``` and run or on BBB run ```i2cdetect -r -y 2```
  - If transmitter does not show up
    - Double check each wire is connectioned correctly 3v3, GND, SDA, and SCL
    - No really, go double check! It can happen to anyone! :)
    - Check each wire's continuity to make sure there isn't a break

### Transmitter's RDS not working well
- Enable Debug logging for the Engine
- Check for read and/or write errors in Dynamic_RDS_Engine.log
  - If errors happen, then I<sup>2</sup>C fails and the Engine exits
    - Check connection and wire continuity between RPi/BBB
    - Disconnect transmitter 12v power if connected and check I<sup>2</sup>C bus
  - If errors happen at random
    - Make sure the PWM wire does NOT along side the I<sup>2</sup>C wires
