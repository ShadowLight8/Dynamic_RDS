<div id="global" class="settings">

<h2>Status</h2>
<?
$i2cbus = 0;
if (file_exists('/dev/i2c-1')) { $i2cbus = 1; }
$engineRunning = true;
if (empty(trim(shell_exec("ps -ef | grep Dynamic_RDS_Engine.py | grep -v grep")))) {
 $engineRunning = false;
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
  $goodStatus = $goodStatus . 'Detected QN8066 on I<sup>2</sup>C bus ' . $i2cbus . ' at address 0x21';
}
if (!$transmitterFound) {
  exec("sudo i2cget -y " . $i2cbus . " 0x63 2>&1", $output1, $return_val1);
  if (implode($output1) != "Error: Read failed") {
    $transmitterFound = true;
    $transmitterType = 'Si4713';
    $goodStatus = $goodStatus . 'Detected Si4713 on I<sup>2</sup>C bus ' . $i2cbus . ' at address 0x63';
  }
}
if (!$transmitterFound) {
  echo '<div class="callout callout-danger">No transmitter detected on I<sup>2</sup>C bus ' . $i2cbus . ' at addresses 0x21 or 0x63</div>';
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
</script>

<?
PrintSettingGroup("DynRDSRDSSettings", "
<div class='callout callout-warning'>
<h4>RDS Style Text Guide</h4>
Available Values: {T} = Title, {A} = Artist, {N} = Track Number, {L} = Track Length as 0:00</br>
Any static text can be used<br />
| (pipe) will split between RDS groups, like a line break<br />
[ ] creates a subgroup such that if <b>ANY</b> substitution in the subgroup is emtpy, the entire subgroup is omitted</br>
Use a \ in front of | { } [ or ] to display those characters</div>
", "", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSTransmitterSettings", "", "", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSAudioSettings", "", "", 1, "Dynamic_RDS");
?>
<?
if (!is_dir('/sys/class/pwm/pwmchip0')) {
  echo '<div class="callout callout-warning">Hardware PWM not available. See bottom of this page for instructions. QN8066 amp power output limited to 0</div>';
}
PrintSettingGroup("DynRDSPowerSettings", "", "", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSPluginActivation", "", "Set when the transmitter is active", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSDebugging", "", "", 1, "Dynamic_RDS");
?>
<h2>QN8066 and Hardware PWM Setup</h2>
<div class="container-fluid settingsTable settingsGroupTable">
In order to use Hardware PWM to control the QN8066 amp power, the following are required:
<ul>
<li>An external, USB sound card must be used as the internal audio must be disabled</li>
<li>Modify the /boot/config.txt file by doing the following</li>
<ul>
<li>Comment out dtparam=audio=on with a #</li>
<li>Add the line dtoverlay=pwm</li>
</ul>
</div>
</div>
