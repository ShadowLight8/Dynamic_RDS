<div id="global" class="settings">
<?
$outputReinstallScript = '';
if (isset($_POST["ReinstallScript"]))
{
 $outputReinstallScript = shell_exec(escapeshellcmd("sudo ".$pluginDirectory."/".$_GET['plugin']."/scripts/fpp_install.sh"));
}
?>
<h2>Status</h2>
<?
if ($outputReinstallScript != '') {  
 echo '<div class="callout callout-default"><b>Reinstall Script Output</b><br />';
 echo $outputReinstallScript;
 echo '</div>';
}
$i2cbus = 1;
if (file_exists('/dev/i2c-2')) {
 $i2cbus = 2;
} elseif (file_exists('/dev/i2c-0')) {
 $i2cbus = 0;
}
$engineRunning = true;
if (empty(trim(shell_exec("ps -ef | grep python.*Dynamic_RDS_Engine.py | grep -v grep")))) {
 $engineRunning = false;
}

if (empty(trim(shell_exec("dpkg -s python3-smbus | grep installed")))) {
  echo '<div class="callout callout-danger">python3-smbus is missing - Uninstall and reinstall from Plugin Manager';
  echo '<br /><form method="post"><button name="ReinstallScript">Try re-running install script</button> It may take up to 1 minute to return.</form></div>';
}

$goodStatus = '';
if ($engineRunning) {
  $goodStatus = 'Dynamic RDS Engine is running<br />';
} else {
    echo '<div class="callout callout-danger">Dynamic RDS Engine is not running - Check logs for errors - Restart of FPPD is recommended</div>';
}

$transmitterFound = false;
exec("sudo i2cget -y " . $i2cbus . " 0x21 2>&1", $output, $return_val);
if (implode($output) != "Error: Read failed") {
  $transmitterFound = true;
  $transmitterType = 'QN8066';
  $goodStatus = $goodStatus . 'Detected <b>QN8066</b> on I<sup>2</sup>C bus ' . $i2cbus . ' at address 0x21';
}
if (!$transmitterFound) {
  exec("sudo i2cget -y " . $i2cbus . " 0x63 2>&1", $output1, $return_val1);
  if (implode($output1) != "Error: Read failed") {
    $transmitterFound = true;
    $transmitterType = 'Si4713';
    $goodStatus = $goodStatus . 'Detected <b>Si4713</b> on I<sup>2</sup>C bus ' . $i2cbus . ' at address 0x63';
  }
}
if (!$transmitterFound) {
  echo '<div class="callout callout-danger">No transmitter detected on I<sup>2</sup>C bus ' . $i2cbus . ' at addresses 0x21 or 0x63<br />';
  echo 'Power cycle or reset of transmitter is recommended. SSH into FPP and run <b>i2cdetect -y ' . $i2cbus . '</b> to check I<sup>2</sup>C status</div>';
}
if ($goodStatus != '') {
  $goodStatus = '<div class="callout callout-success">' . $goodStatus . '</div>';
  echo $goodStatus;
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
</script>

<?
PrintSettingGroup("DynRDSRDSSettings", "
<div class='callout callout-default'>
<h3>RDS Style Text Guide</h3>
Values from File Tags or Track Info
<ul><li>{T} = Title</li>
<li>{A} = Artist</li>
<li>{N} = Track Number</li>
<li>{L} = Track Length as 0:00</li></ul>
Other Values
<ul><li>{C} = Item count in Main Playlist section</li></ul>
Any static text can be used<br />
| (pipe) will split between RDS groups, like a line break<br />
[ ] creates a subgroup such that if <b>ANY</b> substitution in the subgroup is emtpy, the entire subgroup is omitted</br>
Use a \ in front of | { } [ or ] to display those characters</div>
", "", 1, "Dynamic_RDS");
PrintSettingGroup("DynRDSTransmitterSettings", "", "", 1, "Dynamic_RDS");
PrintSettingGroup("DynRDSAudioSettings", "", " <i class='fas fa-fw fa-bolt fa-nbsp ui-level-1'></i>indicates a live change to transmitter, no FPP restart required", 1, "Dynamic_RDS", "DynRDSFastUpdate");
if (!is_dir('/sys/class/pwm/pwmchip0')) {
  echo '<div class="callout callout-warning">Hardware PWM not available. See bottom of this page for instructions. QN8066 amp power output limited to 0</div>';
}
PrintSettingGroup("DynRDSPowerSettings", "", "", 1, "Dynamic_RDS");
PrintSettingGroup("DynRDSPluginActivation", "", "Set when the transmitter is active", 1, "Dynamic_RDS");
if (!(is_file('/bin/mpc') || is_file('/usr/bin/mpc'))) {
  echo '<div class="callout callout-warning">MPC not detected. Functionality not available.</div>';
}
PrintSettingGroup("DynRDSmpc", "", "Pull RDS data from MPC / After Hours Music plugin when idle", 1, "Dynamic_RDS", "DynRDSFastUpdate");
PrintSettingGroup("DynRDSDebugging", "", "", 1, "Dynamic_RDS", "DynRDSFastUpdate");
?>
<h2>Logs</h2>
<div class="container-fluid settingsTable settingsGroupTable">
<p>Dynamic_RDS_callbacks.log <input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_callbacks.log', 'Dynamic_RDS/Dynamic_RDS_callbacks.log');" id="btnViewScript" class="buttons" type="button" value="View All" />
<input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_callbacks.log?tail=100', 'Dynamic_RDS/Dynamic_RDS_callbacks.log');" id="btnViewScript" class="buttons" type="button" value="View Recent" /></p>
<p>Dynamic_RDS_Engine.log <input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_Engine.log', 'Dynamic_RDS/Dynamic_RDS_Engine.log');" id="btnViewScript" class="buttons" type="button" value="View All" />
<input onclick= "ViewFileImpl('api/file/plugins/Dynamic_RDS/Dynamic_RDS_Engine.log?tail=100', 'Dynamic_RDS/Dynamic_RDS_Engine.log');" id="btnViewScript" class="buttons" type="button" value="View Recent" /></p>
</div>
<br />
<h2>QN8066 and Hardware PWM Setup</h2>
<div class="container-fluid settingsTable settingsGroupTable">
In order to use Hardware PWM to control the QN8066 amp power, the following are required
<ul>
<li>An external, USB sound card must be used as the internal audio must be disabled</li>
<li>Modify the /boot/config.txt file by doing the following</li>
<ul>
<li>Comment out dtparam=audio=on with a #</li>
<li>Add the line dtoverlay=pwm</li>
</ul>
</div>
</div>
