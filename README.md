# Dynamic_RDS - FM Transmitter Plugin for Falcon Player

> [!NOTE]
> Supports **QN8066** and **Si4713** FM transmitter chips

Created for Falcon Player 6.0+ (FPP) as a plugin to generate RDS (radio data system) messages similar to what is seen from typical FM stations. The RDS messages are fully customizable with static text, breaks, and grouping along with the supported file tag data fields of title, artist, album, genre, track number, and track length, as well as main playlist position and item count. Currently, the plugin supports the QN8066 chip and the Si4173 chip. The chips are controlled via the I<sup>2</sup>C bus.

## Si4713 transmitter board
Originally, the Si4713 breakout board was available from [AdaFruit](https://www.adafruit.com/product/1958) but it now out of stock. There are many clones of this board that can be found on [AliExpress](https://www.aliexpress.us/w/wholesale-Si4713-transmitter.html) or by a [Google Search](https://www.google.com/search?q=Si4713+transmitter)

> [!NOTE]
> To reduce system load, the on-board buffers of the Si4713 are used by this plugin. The trade off is not being able to directly control the timing of each RDS message.

![Si4713 Breakout Board](images/Si4713-transmitter.jpg)

## QN8066 transmitter board
> [!IMPORTANT]
> There are other similar looking boards, so double check for the QN8066 chip. For a detailed look at identifying QN8066 boards, check out [Spectraman's video](https://www.youtube.com/watch?v=i8re0nc_FdY&t=1017s).

[Aliexpress link to purchase QN8066 FM Transmitter](https://a.aliexpress.com/_mLTpVqO)

![Radio Board with Screen](images/radio_board_w_screen.jpeg)
![Radio Board](images/radio_board.jpeg)
![Radio Board Pinout](images/radio_board_pinout.jpeg)

### Antenna
The QN8066 transmitter board needs an antenna for safe operations.

* Small bench testing option - https://www.amazon.com/gp/product/B07K7DBVX9
* 1/4 wave ground plane antenna calculator - https://m0ukd.com/calculators/quarter-wave-ground-plane-antenna-calculator/
* Show ready option 1/4 wave - https://www.amazon.com/Transmitter-Professional-87-108mhz-0-5w-100w-Waterproof/dp/B09NDPY4JG
* Inexpensive 1/4 wave option - https://www.aliexpress.us/item/2251832695723994.html
* BNC to BNC cable - https://www.amazon.com/gp/product/B0BVVVRYZL/)

(More detail to be added)

### Cables, Connectors, and Shielding
> [!CAUTION]
> Do not run the PWM wire along side the I<sup>2</sup>C wires. During testing this caused failures in the I<sup>2</sup>C commands as soon as PWM was enabled.

#### Connector info
* The connection on the transmitter board is a 5-pin JST-XH type connector, 2.54mm.
* The Raspberry Pis use a female Dupont connector and we recommended using a 2 x 6 block connector.
* The BeagleBone Blacks (BBB) use a male Dupont connector (recommendation pending BBB support work in progress).

If you are comfortable with crimping and making connectors, here are examples of what to use
* JST-XH connectors - https://www.amazon.com/dp/B015Y6JOUG
* Dupont connectors - https://www.amazon.com/dp/B0774NMT1S
* Single kit with both JST-XH and Dupont connectors - https://www.amazon.com/dp/B09Q5MPM7H/
* JST-XH kit with Crimping Tool - https://www.amazon.com/gp/product/B094XSF2GK

Pre-crimped wires are also an options
* JST-XH Pre-crimped wires - https://www.amazon.com/dp/B0BW9TJN21
* Dupont Pre-crimped wires - https://www.amazon.com/dp/B07GD1W1VL

#### Cable for a Raspberry Pi

![Raspberry Pi Connection](images/raspberry_pi_connection.jpeg)
![Raspberry Pi to Radio](images/radio_board_and_pi_pinout.jpeg)
![Custom RPi to QN8066 Cable](images/RPi_to_QN8066_cable.jpeg)

The green PWM wire runs next to yellow 3.3V and orange GND wire until right before the end to eliminate issue with interference. Keeping the cable as short as possible helps to reduce interference.

#### Cable for a BeagleBone Black (BBB)
(Support for the BBB is still in progress)

#### Shielding and RF interference
Given the nature of an FM transmitter, interference is potential problem. This interference commonly shows up as I<sup>2</sup>C errors which become more frequent as transmitter power increases. Moving the antenna away from the RPi/BBB and the transmitter board can reduce this. A significantly more robust setup it to locate the RPi/BBB and transmitter board inside a grounded, metal case such as was done by @chrkov here:
![Grounded case setup](images/pi_transmitter_setup1.jpg)
![Grounded case setup](images/pi_transmitter_setup2.jpg)

### Using Hardware PWM on Raspberry Pi
The recommended QN8066 transmitter board can take a PWM signal to increase its power output. Be sure to comply with all applicable laws related to FM broadcasts.

> [!CAUTION]
> Do not run the PWM wire along side the I<sup>2</sup>C wires. During testing this caused failures in the I<sup>2</sup>C commands as soon as PWM was enabled.

On the Raspberry Pi, in order to use the hardware PWM, the built-in analog audio must be disabled and an external USB sound card or DAC is required. The built-in audio uses both hardware PWM channels to generate the audio, so PWM cannot be used for other purposes when enabled. Software PWM is also an option, but at an increased CPU cost and a decrease in duty cycle accuracy.

From the Dynamic RDS configuration page, under the Power Settings, enable PWM.

This will automatically modify the /boot/firmware/config.txt:
1. Comment out all ```dtparm=audio=on``` lines with a #
2. Add the line ```dtoverlay=pwm,pin=18,func=2``` by default
Under the Advanced Options at the bottom of the configuration page, the output pin can be selected. This is also where Software PWM can be selected on most other pins.

> [!TIP]
> Don't forget to change the Audio Output Device in the FPP Settings to use the USB sound card or DAC

## Integration with FPP After Hours Music Plugin
The Dynamic RDS plugin has the ability to work in conjunction with the [FPP After Hours Music Plugin](https://github.com/jcrossbdn/fpp-after-hours) to provide RDS Data from an internet stream of music. The information from the stream is populated in the Title field.

Once the After Hours Music Plugin is installed, the integration can be enabled on the Dynamic RDS configuration pages in the MPC / After Hours Music section.

![MPC-After-Hours](https://user-images.githubusercontent.com/23623446/201971100-7a213ef5-a22d-4e76-a545-8c8c9724a9e0.JPG)

## Scripting Plugin Changes
It is an option to use scripts to change Dynamic RDS option value. As an example, this could be used to change the PS and/or RT style text to be different during the show verses after. The following is a bash script that can update the style text and have the plugin start using it without restarting FPP.
```
#!/bin/bash
curl -d 'Merry|Christ-|  -mas!|{T}|{A}|[{N} of {C}]' -X POST http://localhost/api/plugin/Dynamic_RDS/settings/DynRDSPSStyle
curl -d 'Merry Christmas! {T}[ by {A}]|[Track {N} of {C}]' -X POST http://localhost/api/plugin/Dynamic_RDS/settings/DynRDSRTStyle
curl http://localhost/api/plugin/Dynamic_RDS/FastUpdate
```
The single quotes around the style text in the script are important so the Linux shell (bash) won't try to interpret what is in there. This example could be saved as a file in the media/scripts folder and then use it with the scheduler (via Command -> Run Script) or playlists.

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
  - If too many errors happen, then I<sup>2</sup>C fails and the Engine exits
    - Reduce the Amp Power
    - Try using Software I<sup>2</sup>C
    - Enclose the RPi/BBB and transmitter in a grounded, metal box with the antenna outside of the box
    - Check connection and wire continuity between RPi/BBB
    - Disconnect transmitter 12v power if connected and check I<sup>2</sup>C bus with `i2cdetect -y 1`
  - If errors happen at random
    - Make sure the PWM wire does NOT run along side the I<sup>2</sup>C wires, interference can occur
    - Try to lower the Chip Power and Amp Power, RF interference can impact I<sup>2</sup>C
    - Move the antenna further away from the transmitter board and RPi/BBB
