<?

function getEndpointsDynamic_RDS() {
    $endpoints = array(
       array('method' => 'GET', 'endpoint' => 'FastUpdate', 'callback' => 'DynRDSFastUpdate'),
       array('method' => 'GET', 'endpoint' => 'Status', 'callback' => 'DynRDSStatus'),
       array('method' => 'POST', 'endpoint' => 'PiBootChange/:SettingName', 'callback' => 'DynRDSPiBootChange'),
       array('method' => 'POST', 'endpoint' => 'ScriptStream', 'callback' => 'DynRDSScriptStream')
    );
    return $endpoints;
}

function DynRDSFastUpdate() {
    shell_exec("sudo /home/fpp/media/plugins/Dynamic_RDS/callbacks.py --update");
}

function DynRDSStatus() {
    $statusFile = __DIR__ . '/Dynamic_RDS_Status.json';

    if (!is_file($statusFile)) {
        return json_encode(['error' => 'No status file - Dynamic RDS Engine may not have started']);
    }

    $status = json_decode(file_get_contents($statusFile), true);
    if (!is_array($status)) {
        return json_encode(['error' => 'Unable to parse status file']);
    }

    // Writes only happen when the broadcast content changes, so file age is not
    // a heartbeat - minutes of silence during a long track is normal. Liveness
    // comes from checking the recorded pid is still a running Engine.
    $status['age'] = time() - filemtime($statusFile);
    $status['running'] = DynRDSEngineAlive($status['pid'] ?? 0);

    return json_encode($status);
}

function DynRDSEngineAlive($pid) {
    $pid = (int)$pid;
    if ($pid <= 0) {
        return false;
    }
    $cmdline = @file_get_contents("/proc/{$pid}/cmdline");
    if ($cmdline === false) {
        return false;
    }
    // Guard against a recycled pid now belonging to an unrelated process
    return str_contains($cmdline, 'Dynamic_RDS_Engine.py');
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
                exec("sudo sed -i -e '/^#dtparam=audio=on/a dtoverlay=pwm,pin=" . escapeshellarg(str_replace(",", ",func=", $myPluginSettings['DynRDSAdvPIPWMPin'])) . "' /boot/firmware/config.txt");
              }
           } else {
              exec("sudo sed -i -e '/^dtoverlay=pwm/d' /boot/firmware/config.txt");
              exec("sudo sed -i -e 's/^#dtparam=audio=on/dtparam=audio=on/' /boot/firmware/config.txt");
           }
           break;

        case 'DynRDSAdvPIPWMPin':
           if (is_numeric(strpos($myPluginSettings['DynRDSAdvPIPWMPin'], ','))) {
              exec("sudo sed -i -e 's/^#dtoverlay=pwm/dtoverlay=pwm/' /boot/firmware/config.txt");
              exec("sudo sed -i -e '/^dtoverlay=pwm/c dtoverlay=pwm,pin=" . escapeshellarg(str_replace(",", ",func=", $myPluginSettings['DynRDSAdvPIPWMPin'])) . "' /boot/firmware/config.txt");
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
