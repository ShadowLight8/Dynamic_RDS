<div id="global" class="settings">
<h1>Status</h1>
<?
$outputReinstallScript = '';
if (isset($_POST["ReinstallScript"])) {
 $outputReinstallScript = shell_exec(escapeshellcmd("sudo ".$pluginDirectory."/".$_GET['plugin']."/scripts/fpp_install.sh"));
}

if ($outputReinstallScript != '') {
 echo '<div class="callout callout-default"><b>Reinstall Script Output</b><br />';
 echo $outputReinstallScript;
 echo '</div>';
}

$errorDetected = false;

if (empty(trim(shell_exec("dpkg -s python3-smbus | grep installed")))) {
  echo '<div class="callout callout-danger">python3-smbus is missing - Uninstall and reinstall from Plugin Manager';
  echo '<br /><form method="post"><button name="ReinstallScript">Try re-running install script</button> It may take up to 1 minute to return.</form></div>';
  $errorDetected = true;
}

$i2cbus = 1;
if (file_exists('/dev/i2c-2')) {
 $i2cbus = 2;
} elseif (file_exists('/dev/i2c-0')) {
 $i2cbus = 0;
} elseif (!file_exists('/dev/i2c-1')) {
 echo '<div class="callout callout-danger">Unable to find an I<sup>2</sup>C bus - Check /boot/config.txt for I<sup>2</sup>C entry</div>';
 $errorDetected = true;
}

$engineRunning = true;
if (empty(trim(shell_exec("ps -ef | grep python.*Dynamic_RDS_Engine.py | grep -v grep")))) {
 sleep(1);
 if (empty(trim(shell_exec("ps -ef | grep python.*Dynamic_RDS_Engine.py | grep -v grep")))) {
  echo '<div class="callout callout-danger">Dynamic RDS Engine is not running - Check logs for errors - Restart of FPPD is recommended</div>';
  $engineRunning = false;
  $errorDetected = true;
 }
}

$transmitterType = '';
$transmitterAddress = '';
if (trim(shell_exec("sudo i2cget -y " . $i2cbus . " 0x21 2>&1")) != "Error: Read failed") {
 $transmitterType = 'QN8066';
 $transmitterAddress = '0x21';
} elseif (trim(shell_exec("sudo i2cget -y " . $i2cbus . " 0x63 2>&1")) != "Error: Read failed") {
 $transmitterType = 'Si4713';
 $transmitterAddress = '0x63';
} else {
  echo '<div class="callout callout-danger">No transmitter detected on I<sup>2</sup>C bus ' . $i2cbus . ' at addresses 0x21 or 0x63<br />';
  echo 'Power cycle or reset of transmitter is recommended. SSH into FPP and run <b>i2cdetect -y ' . $i2cbus . '</b> to check I<sup>2</sup>C status</div>';
  $errorDetected = true;
}

if (isset($pluginSettings['DynRDSQN8066PIHardwarePWM']) && $pluginSettings['DynRDSQN8066PIHardwarePWM'] == 1) {
 if (shell_exec("lsmod | grep 'snd_bcm2835.*1\>'")) {
  echo '<div class="callout callout-warning">On-board sound card appears active and will interfere with hardware PWM. Try a reboot first, next toggle the Enable PI Hardware PWM setting below and reboot. If issues persist check /boot/config.txt and comment out dtparam=audio=on</div>';
 }
 if (empty(shell_exec("lsmod | grep pwm")) || !file_exists('/sys/class/pwm/pwmchip0')) {
  echo '<div class="callout callout-warning">Hardware PWM has not been loaded. Try a reboot first, next toggle the Enable PI Hardware PWM setting below and reboot. If issues persist then check /boot/config.txt and add dtoverlay=pwm</div>';
 }
}

$i2cBusType = 'hardware';
if (isset($pluginSettings['DynRDSAdvPISoftwareI2C']) && $pluginSettings['DynRDSAdvPISoftwareI2C'] == 1) {
 $i2cBusType = 'software';
 if (shell_exec("lsmod | grep i2c_bcm2835")) {
  echo '<div class="callout callout-warning">Hardware I<sup>2</sup>C appears active. Try a reboot first, next toggle the Use PI Software I2C setting below and reboot. If issues persist check /boot/config.txt and comment out dtparam=i2c_arm=on</div>';
  $i2cBusType = 'hardware';
 }
 if (empty(shell_exec("lsmod | grep i2c_gpio"))) {
  echo '<div class="callout callout-warning">Software I<sup>2</sup>C has not been loaded. Try a reboot first, next toggle the Use PI Software I2C setting below and reboot. If issues persist then check /boot/config.txt and add dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1</div>';
 }
} else {
 if (shell_exec("lsmod | grep i2c_gpio")) {
  echo '<div class="callout callout-warning">Software I<sup>2</sup>C appears active. Try a reboot first, next toggle the Use PI Software I2C setting below and reboot. If issues persist check /boot/config.txt and comment out dtoverlay=i2c-gpio,i2c_gpio_sda=2,i2c_gpio_scl=3,i2c_gpio_delay_us=4,bus=1</div>';
  $i2cBusType = 'software';
 }
 if (empty(shell_exec("lsmod | grep i2c_bcm2835"))) {
  echo '<div class="callout callout-warning">Hardware I<sup>2</sup>C has not been loaded. Try a reboot first, next toggle the Use PI Software I2C setting below and reboot. If issues persist then check /boot/config.txt and add dtparam=i2c_arm=on</div>';
 }
}

if ($engineRunning || $transmitterType != '') {
 echo '<div class="callout callout-success">';
 if ($engineRunning) {
  echo '<div>Dynamic RDS Engine is running</div>';
 }
 if ($transmitterType != '') {
  echo '<div>Detected <b>' . $transmitterType . '</b> on I<sup>2</sup>C ' . $i2cBusType . ' bus ' . $i2cbus . ' at address ' . $transmitterAddress . '</div>';
 }
 echo '</div>';
}
?>

<script>
window.onload = function() {
  var transmitterSelect = document.getElementById("DynRDSTransmitter");
  if (transmitterSelect.value === "None") {
    transmitterSelect.value = <? echo '"' . $transmitterType . '"' ?>;
    transmitterSelect.onchange();
  }
};

function DynRDSFastUpdate() {
  $.get('api/plugin/Dynamic_RDS/FastUpdate');
}

function DynRDSPiBootUpdate(key) {
  $.post('api/plugin/Dynamic_RDS/PiBootChange/' + key, JSON.stringify(Object.assign({},pluginSettings)));
  // Object.assign({},pluginSettings) converts to an object from an associative array. Very likely pluginSettings could be changed
  // to be an object instead of an array in FPP's code
}
</script>

<?
PrintSettingGroup("DynRDSRDSSettings", "
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
[ ] creates a subgroup such that if <b>ANY</b> substitution in the subgroup is emtpy, the entire subgroup is omitted<br />
Use a \ in front of | { } [ or ] to display those characters<br />
End of the style text will implicitly function as a line break</div>
", "", 1, "Dynamic_RDS");

PrintSettingGroup("DynRDSTransmitterSettings", "", "", 1, "Dynamic_RDS");

PrintSettingGroup("DynRDSAudioSettings", "", "<i class='fas fa-fw fa-bolt fa-nbsp ui-level-1'></i>indicates a live change to transmitter, no FPP restart required", 1, "Dynamic_RDS", "DynRDSFastUpdate");

PrintSettingGroup("DynRDSPowerSettings", "", "", 1, "Dynamic_RDS", "DynRDSPiBootUpdate");

PrintSettingGroup("DynRDSPluginActivation", "", "Set when the transmitter is active", 1, "Dynamic_RDS");

if (!(is_file('/bin/mpc') || is_file('/usr/bin/mpc'))) {
  echo '<div class="callout callout-warning">MPC not detected. Functionality not available.</div>';
}
PrintSettingGroup("DynRDSmpc", "", "Pull RDS data from MPC / After Hours Music plugin when idle", 1, "Dynamic_RDS", "DynRDSFastUpdate");

PrintSettingGroup("DynRDSLogLevel", "", "", 1, "Dynamic_RDS", "DynRDSFastUpdate");
?>
<h2>View Logs</h2>
<div class="container-fluid settingsTable settingsGroupTable">
<p>Dynamic_RDS_callbacks.log <input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_callbacks.log', 'Dynamic_RDS/Dynamic_RDS_callbacks.log');" id="btnViewScript" class="buttons" type="button" value="View All" />
<input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_callbacks.log?tail=100', 'Dynamic_RDS/Dynamic_RDS_callbacks.log');" id="btnViewScript" class="buttons" type="button" value="View Recent" /></p>
<p>Dynamic_RDS_Engine.log <input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_Engine.log', 'Dynamic_RDS/Dynamic_RDS_Engine.log');" id="btnViewScript" class="buttons" type="button" value="View All" />
<input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_Engine.log?tail=100', 'Dynamic_RDS/Dynamic_RDS_Engine.log');" id="btnViewScript" class="buttons" type="button" value="View Recent" /></p>
</div>
<br />
<?
PrintSettingGroup("DynRDSAdv", "", "", 1, "Dynamic_RDS", "DynRDSPiBootUpdate");
?>
</div>
