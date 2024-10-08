<?

function getEndpointsDynamic_RDS() {
    $endpoints = array(
       array('method' => 'GET', 'endpoint' => 'FastUpdate', 'callback' => 'DynRDSFastUpdate'),
       array('method' => 'POST', 'endpoint' => 'PiBootChange/:SettingName', 'callback' => 'DynRDSPiBootChange'),
       array('method' => 'POST', 'endpoint' => 'ScriptStream', 'callback' => 'DynRDSScriptStream')
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
              exec("sudo sed -i -e 's/^dtparam=i2c_arm=on/#dtparam=i2c_arm=on/' /boot/firmware/config.txt");
              exec("sudo sed -i -e '/^#dtparam=i2c_arm=on/a dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1' /boot/firmware/config.txt");
           } else {
              exec("sudo sed -i -e '/^dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1/d' /boot/firmware/config.txt");
              exec("sudo sed -i -e 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/' /boot/firmware/config.txt");
           }
           break;

        case 'DynRDSQN8066PIPWM':
           if (strcmp($myPluginSettings[$settingName],'1') == 0) {
              exec("sudo sed -i -e 's/^dtparam=audio=on/#dtparam=audio=on/' /boot/firmware/config.txt");
              if (is_numeric(strpos($myPluginSettings['DynRDSAdvPIPWMPin'], ','))) {
                exec("sudo sed -i -e '/^#dtparam=audio=on/a dtoverlay=pwm,pin=" . str_replace(",", ",func=", $myPluginSettings['DynRDSAdvPIPWMPin']) . "' /boot/firmware/config.txt");
              }
           } else {
              exec("sudo sed -i -e '/^dtoverlay=pwm/d' /boot/firmware/config.txt");
              exec("sudo sed -i -e 's/^#dtparam=audio=on/dtparam=audio=on/' /boot/firmware/config.txt");
           }
           break;

        case 'DynRDSAdvPIPWMPin':
           if (is_numeric(strpos($myPluginSettings['DynRDSAdvPIPWMPin'], ','))) {
              exec("sudo sed -i -e 's/^#dtoverlay=pwm/dtoverlay=pwm/' /boot/firmware/config.txt");
              exec("sudo sed -i -e '/^dtoverlay=pwm/c dtoverlay=pwm,pin=" . str_replace(",", ",func=", $myPluginSettings['DynRDSAdvPIPWMPin']) . "' /boot/firmware/config.txt");
           } else {
              exec("sudo sed -i -e 's/^dtoverlay=pwm/#dtoverlay=pwm/' /boot/firmware/config.txt");
           }
           break;

        case 'DynRDSQN8066AmpPower':
           DynRDSFastUpdate();
           break;

        default:
           DynRDSFastUpdate();
    }
}

function DynRDSScriptStream() {
    $postData = json_decode(file_get_contents('php://input'), true);

    DisableOutputBuffering();

    switch ($postData['script']) {
        case 'dependencies':
           system('~/media/plugins/Dynamic_RDS/scripts/fpp_install.sh', $return_val);
           break;
        case 'python3-paho-mqtt':
           system('~/media/plugins/Dynamic_RDS/scripts/paho_install.sh', $return_val);
           break;
        default:
           return "\nUnknown script\n";
    }
    return "\nDone\n";
}
?>
