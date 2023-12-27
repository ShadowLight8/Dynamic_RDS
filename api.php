<?

function getEndpointsDynamic_RDS() {
    $result = array();

    $ep = array(
        'method' => 'GET', 'endpoint' => 'FastUpdate', 'callback' => 'DynRDSFastUpdate',
        'method' => 'POST', 'endpoint' => 'PiBootChange/:SettingName', 'callback' => 'DynRDSPiBootChange'
    );

    array_push($result, $ep);

    return $result;
}

function DynRDSFastUpdate() {
    shell_exec(escapeshellcmd("sudo /home/fpp/media/plugins/Dynamic_RDS/callbacks.py --update"));

    $result = array();
    $result['version'] = 'Dynamic RDS 1.0.0';

    return json($result);
}

function DynRDSPiBootChange() {
    $settingName = params('SettingName');
    $value = json_decode(file_get_contents('php://input'));

    shell_exec("echo --- >> ~/test.txt");
    shell_exec("echo " . $settingName . " >> ~/test.txt");
    shell_exec("echo " . $value . " >> ~/test.txt");

    switch ($settingName) {
        case 'DynRDSAdvSoftwareI2C':
           if (strcmp($value,'1') == 0) {
              exec("sudo sed -i -e 's/^dtparam=i2c_arm=on/#dtparam=i2c_arm=on/' /boot/config.txt");
              exec("sudo sed -i -e '/^#dtparam=i2c_arm=on/a dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1' /boot/config.txt");
           } else {
              exec("sudo sed -i -e '/^dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1/d' /boot/config.txt");
              exec("sudo sed -i -e 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/config.txt");
           }
           break;
        case 'DynRDSQN8066PIHardwarePWM':
           if (strcmp($value,'1') == 0) {
              exec("sudo sed -i -e 's/^dtparam=audio=on/#dtparam=audio=on/' /boot/config.txt");
              exec("sudo sed -i -e '/^#dtparam=audio=on/a dtoverlay=pwm' /boot/config.txt");
           } else {
              exec("sudo sed -i -e '/^dtoverlay=pwm/d' /boot/config.txt");
              exec("sudo sed -i -e 's/^#dtparam=audio=on/dtparam=audio=on/' /boot/config.txt");
           }
           break;
        default:
           shell_exec("echo ? " . $settingName . " >> ~/test.txt");
           shell_exec("echo ? " . $value . " >> ~/test.txt");
    }
}
?>
