<?

function getEndpointsDynamic_RDS() {
    $endpoints = array(
       array('method' => 'GET', 'endpoint' => 'FastUpdate', 'callback' => 'DynRDSFastUpdate'),
       array('method' => 'POST', 'endpoint' => 'PiBootChange/:SettingName', 'callback' => 'DynRDSPiBootChange')
    );
    return $endpoints;
}

function DynRDSFastUpdate() {
    shell_exec("sudo /home/fpp/media/plugins/Dynamic_RDS/callbacks.py --update");
}

function DynRDSPiBootChange() {
    $settingName = params('SettingName');
    $myPluginSettings = json_decode(file_get_contents('php://input'), true);

    switch ($settingName) {
        case 'DynRDSAdvPISoftwareI2C':
           if (strcmp($myPluginSettings[$settingName],'1') == 0) {
              exec("sudo sed -i -e 's/^dtparam=i2c_arm=on/#dtparam=i2c_arm=on/' /boot/config.txt");
              exec("sudo sed -i -e '/^#dtparam=i2c_arm=on/a dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1' /boot/config.txt");
           } else {
              exec("sudo sed -i -e '/^dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1/d' /boot/config.txt");
              exec("sudo sed -i -e 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/config.txt");
           }
           break;

        case 'DynRDSQN8066PIHardwarePWM':
           if (strcmp($myPluginSettings[$settingName],'1') == 0) {
              exec("sudo sed -i -e 's/^dtparam=audio=on/#dtparam=audio=on/' /boot/config.txt");
              exec("sudo sed -i -e '/^#dtparam=audio=on/a dtoverlay=pwm,pin=" . str_replace(",", ",func=", $myPluginSettings['DynRDSAdvPIPWMPin']) . "' /boot/config.txt");
           } else {
              exec("sudo sed -i -e '/^dtoverlay=pwm/d' /boot/config.txt");
              exec("sudo sed -i -e 's/^#dtparam=audio=on/dtparam=audio=on/' /boot/config.txt");
           }
           break;

        case 'DynRDSAdvPIPWMPin':
           exec("sudo sed -i -e '/^dtoverlay=pwm/c dtoverlay=pwm,pin=" . str_replace(",", ",func=", $myPluginSettings['DynRDSAdvPIPWMPin']) . "' /boot/config.txt");
           break;

        case 'DynRDSQN8066AmpPower':
           DynRDSFastUpdate();
           break;
    }
}
?>
