<?php
declare(strict_types=1);

enum TransmitterType: string {
    case NONE = 'None';
    case QN8066 = 'QN8066';
    case SI4713 = 'Si4713';

    public function getI2CAddress(): int {
        return match($this) {
            self::QN8066 => 0x21,
            self::SI4713 => 0x63,
            self::NONE => 0x00,
        };
    }

    public function getAddressHex(): string {
        return sprintf('0x%02x', $this->getI2CAddress());
    }
}

enum PlatformType: string {
    case RASPBERRY_PI = 'RaspberryPi';
    case BEAGLEBONE_BLACK = 'BeagleBoneBlack';
    case UNKNOWN = 'Unknown';

    public static function detect(): self {
        if (file_exists('/boot/firmware/config.txt')) {
            return self::RASPBERRY_PI;
        }
        if (file_exists('/boot/uEnv.txt')) {
            return self::BEAGLEBONE_BLACK;
        }
        return self::UNKNOWN;
    }

    public function getConfigFile(): ?string {
        return match($this) {
            self::RASPBERRY_PI => '/boot/firmware/config.txt',
            self::BEAGLEBONE_BLACK => '/boot/uEnv.txt',
            self::UNKNOWN => null,
        };
    }
}

class DynamicRDSStatus {
    private array $errors = [];
    private array $warnings = [];
    private array $successes = [];

    public function addError(string $message): void {
        $this->errors[] = $message;
    }

    public function addWarning(string $message): void {
        $this->warnings[] = $message;
    }

    public function addSuccess(string $message): void {
        $this->successes[] = $message;
    }

    public function hasErrors(): bool {
        return !empty($this->errors);
    }

    public function displayMessages(): void {
        foreach ($this->errors as $error) {
            echo '<div class="callout callout-danger">' . $error . '</div>';
        }

        foreach ($this->warnings as $warning) {
            echo '<div class="callout callout-warning">' . $warning . '</div>';
        }

        if (!empty($this->successes)) {
            echo '<div class="callout callout-success">';
            foreach ($this->successes as $success) {
                echo '<div>' . $success . '</div>';
            }
            echo '</div>';
        }
    }
}

class ShellCommandExecutor {
    public static function execute(string $command, array $args = []): string {
        $escapedArgs = array_map('escapeshellarg', $args);
        $fullCommand = sprintf($command, ...$escapedArgs);
        return shell_exec($fullCommand) ?? '';
    }

    public static function isEmpty(string $output): bool {
        return empty(trim($output));
    }
}

class I2CDetector {
    private int $bus;

    public function __construct(int $bus) {
        if ($bus < 0) {
            throw new \InvalidArgumentException("Invalid I2C bus: {$bus}");
        }
        $this->bus = $bus;
    }

    public function detectTransmitter(): TransmitterType {
        // Check QN8066 at 0x21
        if ($this->isDevicePresent(0x21)) {
            return TransmitterType::QN8066;
        }

        // Check Si4713 at 0x63
        if ($this->isDevicePresent(0x63)) {
            return TransmitterType::SI4713;
        }

        return TransmitterType::NONE;
    }

    private function isDevicePresent(int $address): bool {
        $cmd = sprintf('sudo i2cget -y %d 0x%02x 2>&1', $this->bus, $address);
        $result = trim(shell_exec($cmd) ?? '');
        return $result !== "Error: Read failed";
    }

    public function getBus(): int {
        return $this->bus;
    }
}

class I2CBusDetector {
    public static function detectBus(PlatformType $platform): int {
        if ($platform === PlatformType::BEAGLEBONE_BLACK && file_exists('/dev/i2c-2')) {
            return 2;
        }

        if (file_exists('/dev/i2c-0')) {
            return 0;
        }

        if (file_exists('/dev/i2c-1')) {
            return 1;
        }

        return -1;
    }
}

class DependencyChecker {
    public static function isPython3SmbusInstalled(): bool {
        $output = ShellCommandExecutor::execute('dpkg -s python3-smbus2 | grep installed');
        return !ShellCommandExecutor::isEmpty($output);
    }

    public static function isPython3gpiozeroInstalled(): bool {
        $output = ShellCommandExecutor::execute('dpkg -s python3-gpiozero | grep installed');
        return !ShellCommandExecutor::isEmpty($output);
    }

    public static function isEngineRunning(): bool {
        $output = ShellCommandExecutor::execute('ps -ef | grep python.*Dynamic_RDS_Engine.py | grep -v grep');
        if (!ShellCommandExecutor::isEmpty($output))
            return !ShellCommandExecutor::isEmpty($output);
        sleep(1);
        $output = ShellCommandExecutor::execute('ps -ef | grep python.*Dynamic_RDS_Engine.py | grep -v grep');
        return !ShellCommandExecutor::isEmpty($output);
    }

    public static function isMPCInstalled(): bool {
        return is_file('/bin/mpc') || is_file('/usr/bin/mpc');
    }

    public static function isPahoMQTTInstalled(): bool {
        return file_exists('/usr/lib/python3/dist-packages/paho') || 
               file_exists('/usr/local/lib/python3.9/dist-packages/paho') ||
               file_exists('/usr/local/lib/python3.11/dist-packages/paho');
    }
}

class RaspberryPiChecker {
    public static function isOnBoardSoundActive(): bool {
        $output = ShellCommandExecutor::execute("lsmod | grep 'snd_bcm2835.*1\\>'");
        return !ShellCommandExecutor::isEmpty($output);
    }

    public static function isHardwarePWMLoaded(): bool {
        return file_exists('/sys/class/pwm/pwmchip0');
    }

    public static function isHardwareI2CActive(): bool {
        $output = ShellCommandExecutor::execute('lsmod | grep -e i2c_bcm2835 -e i2c_designware_core');
        return !ShellCommandExecutor::isEmpty($output);
    }

    public static function isSoftwareI2CActive(): bool {
        $output = ShellCommandExecutor::execute('lsmod | grep i2c_gpio');
        return !ShellCommandExecutor::isEmpty($output);
    }
}

class ZipDownloader {
    private string $dynRDSDir;
    private string $configDirectory;

    public function __construct(string $dynRDSDir, string $configDirectory) {
        $this->dynRDSDir = $dynRDSDir;
        $this->configDirectory = $configDirectory;
    }

    public function createAndDownload(): void {
        $zip = new ZipArchive();
        $zipName = $this->dynRDSDir . "/Dynamic_RDS_logs_config_" . date("YmdHis") . ".zip";

        if ($zip->open($zipName, ZipArchive::CREATE) !== true) {
            echo '<div class="callout callout-danger">Unable to create ZIP file</div>';
            return;
        }

        try {
            $this->addFileToZip($zip, $this->dynRDSDir . "/Dynamic_RDS_callbacks.log", "Dynamic_RDS_callbacks.log");
            $this->addFileToZip($zip, $this->dynRDSDir . "/Dynamic_RDS_Engine.log", "Dynamic_RDS_Engine.log");
            $this->addFileToZip($zip, $this->configDirectory . "/plugin.Dynamic_RDS", "plugin.Dynamic_RDS");
            $this->addFileToZip($zip, "/boot/firmware/config.txt", "config.txt");
            $this->addFileToZip($zip, "/boot/uEnv.txt", "uEnv.txt");

            // Add plugin version info
            $version = ShellCommandExecutor::execute('git -C %s rev-parse --short HEAD', [$this->dynRDSDir]);
            $zip->addFromString('Dynamic_RDS_version.txt', $version);
            $zip->close();
            $this->downloadFile($zipName);
        } finally {
            if (file_exists($zipName)) {
                unlink($zipName);
            }
        }
    }

    private function addFileToZip(ZipArchive $zip, string $filePath, string $zipPath): void {
        if (is_file($filePath)) {
            $zip->addFile($filePath, $zipPath);
        }
    }

    private function downloadFile(string $filePath): void {
        if (!is_file($filePath)) {
            return;
        }

        header("Content-Disposition: attachment; filename=\"" . basename($filePath) . "\"");
        header("Content-Type: application/octet-stream");
        header("Content-Length: " . filesize($filePath));
        header("Connection: close");
        flush();
        readfile($filePath);
    }
}

function renderDynamicRDSStatus(
    string $pluginDirectory,
    string $configDirectory,
    array $pluginSettings,
    array $settings
): void {
    $status = new DynamicRDSStatus();

    // Handle page display
    $noPage = isset($_GET['nopage']);

    if (!$noPage) {
        echo '<div id="global" class="settings">';
        echo '<style>code { color: black; background-color: #f5f5f5; padding: 2px 4px; border-radius: 3px;}</style>';
        echo '<h1>Status</h1>';
    }

    // Detect platform
    $platform = PlatformType::detect();
    $dynRDSDir = $pluginDirectory . '/' . ($_GET['plugin'] ?? 'Dynamic_RDS');

    // Handle ZIP download
    if (isset($_POST["DownloadZip"])) {
        $zipDownloader = new ZipDownloader($dynRDSDir, $configDirectory);
        $zipDownloader->createAndDownload();
        exit;
    }

    // Check dependencies
    if (!DependencyChecker::isPython3SmbusInstalled()) {
        $status->addError('python3-smbus2 is missing <button name="ReinstallScript" onClick="DynRDSScriptStream(\'dependencies\')">Reinstall plugin dependencies</button>');
    }

    if ($platform === PlatformType::RASPBERRY_PI && !DependencyChecker::isPython3gpiozeroInstalled()) {
        $status->addError('python3-gpiozero is missing <button name="ReinstallScript" onClick="DynRDSScriptStream(\'dependencies\')">Reinstall plugin dependencies</button>');
    }

    // Detect I2C bus
    $i2cBus = I2CBusDetector::detectBus($platform);
    if ($i2cBus === -1) {
        $status->addError('Unable to find an I<sup>2</sup>C bus - On RPi, check <code>/boot/firmware/config.txt</code> for I<sup>2</sup>C entry');
    }

    // Detect transmitter
    $transmitterType = TransmitterType::NONE;
    if ($i2cBus !== -1) {
        try {
            $i2cDetector = new I2CDetector($i2cBus);
            $transmitterType = $i2cDetector->detectTransmitter();

            if ($transmitterType === TransmitterType::NONE) {
                $status->addError(
                    'No transmitter detected on I<sup>2</sup>C bus ' . $i2cBus .
                    ' at addresses 0x21 (QN8066) or 0x63 (Si4713)<br />' .
                    'Power cycle or reset of transmitter is recommended. ' .
                    'SSH into FPP and run <code>i2cdetect -y -r ' . $i2cBus . '</code> to check I<sup>2</sup>C status',
                );
            }
        } catch (\Exception $e) {
            $status->addError('Error detecting transmitter: ' . htmlspecialchars($e->getMessage(), ENT_QUOTES, 'UTF-8'));
        }
    }

    // Check engine status
    $engineRunning = DependencyChecker::isEngineRunning();
    if (!$engineRunning) {
        $status->addError('Dynamic RDS Engine is not running - Check logs for errors - Restart of FPPD is recommended');
    }

    if ($platform === PlatformType::RASPBERRY_PI) {
        checkRaspberryPiConfiguration($status, $pluginSettings);
    }

    // Add success messages
    if ($engineRunning) {
        $status->addSuccess('Dynamic RDS Engine is running');
    }

    if ($transmitterType !== TransmitterType::NONE) {
        $i2cType = determineI2CType($platform, $pluginSettings);
        $status->addSuccess(
            'Detected <b>' . $transmitterType->value . '</b> on I<sup>2</sup>C ' . 
            $i2cType . ' bus ' . $i2cBus . ' at address ' . $transmitterType->getAddressHex()
        );
    }

    // Display all status messages
    $status->displayMessages();

    // Output JavaScript
    outputJavaScript($transmitterType);

    // Display settings groups
    displaySettingsGroups($settings);

    if (!$noPage) {
        echo '</div>';
    }
}

/**
 * Check Raspberry Pi specific configuration
 */
function checkRaspberryPiConfiguration(DynamicRDSStatus $status, array $pluginSettings): void {
    // Check PWM configuration
    if (isset($pluginSettings['DynRDSQN8066PIPWM']) &&
        $pluginSettings['DynRDSQN8066PIPWM'] == 1 &&
        isset($pluginSettings['DynRDSAdvPIPWMPin']) &&
        str_contains($pluginSettings['DynRDSAdvPIPWMPin'], ',')) {

        if (RaspberryPiChecker::isOnBoardSoundActive()) {
            $status->addWarning(
                'On-board sound card appears active and will interfere with hardware PWM. ' .
                'Try a reboot first, next toggle the Enable PI Hardware PWM setting below and reboot. ' .
                'If issues persist check <code>/boot/firmware/config.txt</code> and comment out <code>dtparam=audio=on</code>',
            );
        }

        if (!RaspberryPiChecker::isHardwarePWMLoaded()) {
            $status->addWarning(
                'Hardware PWM has not been loaded. Try a reboot first, ' .
                'next toggle the Enable PI Hardware PWM setting below and reboot. ' .
                'If issues persist then check <code>/boot/firmware/config.txt</code> and add <code>dtoverlay=pwm</code>',
            );
        }
    }

    // Check I2C configuration
    checkI2CConfiguration($status, $pluginSettings);
}

/**
 * Check I2C configuration (hardware vs software)
 */
function checkI2CConfiguration(DynamicRDSStatus $status, array $pluginSettings): void {
    $useSoftwareI2C = isset($pluginSettings['DynRDSAdvPISoftwareI2C']) &&
                      $pluginSettings['DynRDSAdvPISoftwareI2C'] == 1;

    if ($useSoftwareI2C) {
        if (RaspberryPiChecker::isHardwareI2CActive()) {
            $status->addWarning(
                'Hardware I<sup>2</sup>C appears active. Try a reboot first, ' .
                'next toggle the Use PI Software I2C setting below and reboot. ' .
                'If issues persist check <code>/boot/firmware/config.txt</code> and comment out <code>dtparam=i2c_arm=on</code>',
            );
        }

        if (!RaspberryPiChecker::isSoftwareI2CActive()) {
            $status->addWarning(
                'Software I<sup>2</sup>C has not been loaded. Try a reboot first, ' .
                'next toggle the Use PI Software I2C setting below and reboot. ' .
                'If issues persist then check <code>/boot/firmware/config.txt</code> and add ' .
                '<br /><code>dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1</code>',
            );
        }
    } else {
        if (RaspberryPiChecker::isSoftwareI2CActive()) {
            $status->addWarning(
                'Software I<sup>2</sup>C appears active. Try a reboot first, ' .
                'next toggle the Use PI Software I2C setting below and reboot. ' .
                'If issues persist check <code>/boot/firmware/config.txt</code> and comment out ' .
                '<br /><code>dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1</code>',
            );
        }

        if (!RaspberryPiChecker::isHardwareI2CActive()) {
            $status->addWarning(
                'Hardware I<sup>2</sup>C has not been loaded. Try a reboot first, ' .
                'next toggle the Use PI Software I2C setting below and reboot. ' .
                'If issues persist then check <code>/boot/firmware/config.txt</code> and add <code>dtparam=i2c_arm=on</code>',
            );
        }
    }
}

/**
 * Determine I2C type (hardware or software)
 */
function determineI2CType(PlatformType $platform, array $pluginSettings): string {
    if ($platform !== PlatformType::RASPBERRY_PI) {
        return 'hardware';
    }

    $useSoftwareI2C = isset($pluginSettings['DynRDSAdvPISoftwareI2C']) && 
                      $pluginSettings['DynRDSAdvPISoftwareI2C'] == 1;

    if ($useSoftwareI2C && RaspberryPiChecker::isSoftwareI2CActive()) {
        return 'software';
    }

    return 'hardware';
}

/**
 * Output JavaScript functions
 */
function outputJavaScript(TransmitterType $transmitterType): void {
    ?>
<script>
window.onload = function() {
    var transmitterSelect = document.getElementById("DynRDSTransmitter");
    if (transmitterSelect && transmitterSelect.value === "None") {
        transmitterSelect.value = <?php echo json_encode($transmitterType->value, JSON_HEX_TAG | JSON_HEX_AMP); ?>;
        transmitterSelect.onchange();
    }
    DynRDSTransmitterFrequencyUpdate();
};

function DynRDSTransmitterFrequencyUpdate() {
    var iconHTML = " <i class='fas fa-fw fa-nbsp ui-level-0'></i>";
    var transmitterSelect = document.getElementById("DynRDSTransmitter");

    if (transmitterSelect && transmitterSelect.value !== "None") {
        var frequencyInput = document.getElementById('DynRDSFrequency');
        var descriptionDiv = document.querySelector('#DynRDSFrequencyRow .description');

        if (frequencyInput && descriptionDiv && transmitterSelect.value === "QN8066") {
            frequencyInput.min = '60';
            descriptionDiv.innerHTML = iconHTML + 'Frequency (60.00-108.00)';
        } else if (frequencyInput && descriptionDiv && transmitterSelect.value === "Si4713") {
            frequencyInput.min = '76';
            descriptionDiv.innerHTML = iconHTML + 'Frequency (76.00-108.00)';
        }
    }
}

function DynRDSFastUpdate() {
    $.get('api/plugin/Dynamic_RDS/FastUpdate');
}

function DynRDSPiBootUpdate(key) {
    $.post('api/plugin/Dynamic_RDS/PiBootChange/' + encodeURIComponent(key), 
           JSON.stringify(Object.assign({}, pluginSettings)));
}

function DynRDSScriptStream(scriptName) {
    var postData = {script: scriptName};
    DisplayProgressDialog('DynRDSScriptStream', 'Install ' + scriptName);
    StreamURL('api/plugin/Dynamic_RDS/ScriptStream', 
              'DynRDSScriptStreamText', 
              'ScriptStreamProgressDialogDone', 
              'ScriptStreamProgressDialogDone', 
              'POST', 
              JSON.stringify(postData));
}

function ScriptStreamProgressDialogDone() {
    $('#DynRDSScriptStreamCloseButton').prop('disabled', false);
    EnableModalDialogCloseButton('DynRDSScriptStream');
}
</script>
    <?php
}

/**
 * Display all settings groups
 */
function displaySettingsGroups(array $settings): void {
    PrintSettingGroup("DynRDSRDSSettings", getRDSStyleGuideHTML(), "", 1, "Dynamic_RDS");

    PrintSettingGroup("DynRDSTransmitterSettings", "", "", 1, "Dynamic_RDS", "DynRDSTransmitterFrequencyUpdate");

    PrintSettingGroup("DynRDSAudioSettings", "",
        "<i class='fas fa-fw fa-bolt fa-nbsp ui-level-1'></i>indicates a live change to transmitter, no FPP restart required",
        1, "Dynamic_RDS", "DynRDSFastUpdate");

    PrintSettingGroup("DynRDSPowerSettings", "", "", 1, "Dynamic_RDS", "DynRDSPiBootUpdate");

    PrintSettingGroup("DynRDSPluginActivation", "", "Set when the transmitter is active", 1, "Dynamic_RDS");

    if (DependencyChecker::isMPCInstalled()) {
        PrintSettingGroup("DynRDSmpc", "",
            "Pull RDS data from MPC / After Hours Music plugin when idle",
            1, "Dynamic_RDS", "DynRDSFastUpdate");
    } else {
        echo '<h2>MPC / After Hours Music</h2>';
        echo '<div class="callout callout-default">Install the After Hours Music Player Plugin to enabled. MPC not detected</div><br />';
    }

    displayMQTTSection($settings);

    PrintSettingGroup("DynRDSLogLevel", "", "", 1, "Dynamic_RDS", "DynRDSFastUpdate");

    displayLogsSection();

    displayReportIssueSection();

    PrintSettingGroup("DynRDSAdv", "", "", 1, "Dynamic_RDS", "DynRDSPiBootUpdate");
}

/**
 * Get RDS Style Guide HTML
 */
function getRDSStyleGuideHTML(): string {
    return <<<'HTML'
<div class='callout callout-default'>
<h3>RDS Style Text Guide</h3>
Values from File Tags or Track Info
<ul><li>{T} = Title</li>
<li>{A} = Artist</li>
<li>{B} = Album</li>
<li>{G} = Genre</li>
<li>{N} = Track Number</li>
<li>{L} = Track Length as 0:00</li></ul>
Main Playlist Section Values
<ul><li>{C} = Item count in Main Playlist section</li>
<li>{P} = Item position or number in Main Playlist section</li></ul>
Any static text can be used<br />
| (pipe) will split between RDS groups, like a line break<br />
[ ] creates a subgroup such that if <b>ANY</b> substitution in the subgroup is empty, the entire subgroup is omitted<br />
Use a \ in front of | { } [ or ] to display those characters<br />
End of the style text will implicitly function as a line break</div>
HTML;
}

/**
 * Display MQTT section
 */
function displayMQTTSection(array $settings): void {
    if (empty($settings['MQTTHost'])) {
        echo '<h2>MQTT</h2>';
        echo '<div class="callout callout-default">Requires that MQTT has been configured under ';
        echo '<a href="settings.php#settings-mqtt">FPP Settings -&gt; MQTT</a></div><br />';
    } elseif (!DependencyChecker::isPahoMQTTInstalled()) {
        echo '<h2>MQTT</h2>';
        echo '<div class="callout callout-default">python3-paho-mqtt is needed to enable MQTT support ';
        echo '<button name="pahoInstall" onClick="DynRDSScriptStream(\'python3-paho-mqtt\');">Install python3-paho-mqtt</button></div>';
    } else {
        $mqttHost = htmlspecialchars($settings['MQTTHost'], ENT_QUOTES, 'UTF-8');
        $mqttPort = htmlspecialchars($settings['MQTTPort'], ENT_QUOTES, 'UTF-8');
        PrintSettingGroup("DynRDSmqtt", "",
            "Broker Host is <b>{$mqttHost}:{$mqttPort}</b>",
            1, "Dynamic_RDS", "");
    }
}

/**
 * Display logs section
 */
function displayLogsSection(): void {
    ?>
<h2>View Logs</h2>
<div class="container-fluid settingsTable settingsGroupTable">
<p>Dynamic_RDS_callbacks.log
<input onclick="ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_callbacks.log', 'Dynamic_RDS/Dynamic_RDS_callbacks.log');"
       class="buttons" type="button" value="View All" />
<input onclick="ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_callbacks.log?tail=50', 'Dynamic_RDS/Dynamic_RDS_callbacks.log');"
       class="buttons" type="button" value="View Recent" /></p>
<p>Dynamic_RDS_Engine.log
<input onclick="ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_Engine.log', 'Dynamic_RDS/Dynamic_RDS_Engine.log');"
       class="buttons" type="button" value="View All" />
<input onclick="ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_Engine.log?tail=50', 'Dynamic_RDS/Dynamic_RDS_Engine.log');"
       class="buttons" type="button" value="View Recent" /></p>
</div>
<br />
    <?php
}

/**
 * Display report issue section
 */
function displayReportIssueSection(): void {
    ?>
<h2>Report an Issue</h2>
<div class="container-fluid settingsTable settingsGroupTable">
<p>
<form action="plugin.php?_menu=status&plugin=Dynamic_RDS&page=Dynamic_RDS.php&nopage" method="post">
<button name="DownloadZip" type="Submit" class="buttons" value="Download log and config zip">
<i class="fas fa-fw fa-nbsp fa-download"></i>Download log and config zip
</button>
</form></p>
<p>Increase the Log Levels to Debug, then create a new issue at <a href="https://github.com/ShadowLight8/Dynamic_RDS/issues"><b>https://github.com/ShadowLight8/Dynamic_RDS/issues</b></a>, describe what you're seeing, and attach the zip file.</p>
Zip file includes:
<ul>
<li>Logs - <code>Dynamic_RDS_callbacks.log</code> and <code>Dynamic_RDS_Engine.log</code></li>
<li>Config - <code>plugin.Dynamic_RDS</code></li>
<li>Version from <code>git rev-parse --short HEAD</code></li>
<li>Pi/BBB boot config - <code>/boot/firmware/config.txt</code> or <code>/boot/uEnv.txt</code></li>
</ul>
</div>
<br />
    <?php
}

renderDynamicRDSStatus(
    pluginDirectory: $pluginDirectory,
    configDirectory: $configDirectory,
    pluginSettings: $pluginSettings,
    settings: $settings
);
?>
