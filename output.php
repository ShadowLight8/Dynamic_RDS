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
  echo '<div class="callout callout-danger">Dynamic RDS Engine is not running - Restart of FPPD is recommended</div>';
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
PrintSettingGroup("DynRDSPluginActivation", "", "Set when the transmitter is active", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSDebugging", "", "", 1, "Dynamic_RDS");
?>

</div>

<hr />
<div id="Si4713Debug" class="settings">
<fieldset>
<p>Dynamic_RDS_callbacks.log: <input onclick= "ViewFile('Logs', '../plugins/Dynamic_RDS/Dynamic_RDS_callbacks.log');" id="btnViewScript" class="buttons" type="button" value="View" /></p>
<p>Dynamic_RDS_Engine.log: <input onclick= "ViewFile('Logs', '../plugins/Dynamic_RDS/Dynamic_RDS_Engine.log');" id="btnViewScript" class="buttons" type="button" value="View" /></p>
</fieldset>
</div>

<div id='fileViewer' title='File Viewer' style="display: none">
  <div id='fileText'>
  </div>
</div>

<br />

<div id="Info" class="settings">
<fieldset>
<legend>Additional Si4713 Information</legend>
<p>Physical connection from Pi -&gt; Si4713<br />
Pin 3 (SDA1) -&gt; SDA<br />
Pin 4 (+5v) -&gt; Vin<br />
Pin 5 (SCL1) -&gt; SCL<br />
Pin 6 (GND) -&gt; GND<br />
Pin 7 (GPIO4) -&gt; RST<br />
USB sound card and a short audio cable to go from the Pi to the Si4713</p>
<p><a href="https://www.adafruit.com/product/1958">Adafruit Si4713 Breakout Board</a></p>
<p><a href="https://www.silabs.com/documents/public/data-sheets/Si4712-13-B30.pdf">Si4713 Datasheet</a></p>
<p><a href="https://www.silabs.com/documents/public/application-notes/AN332.pdf">Si4713 Programming Guide</a></p>
<p><a href="https://www.silabs.com/documents/public/user-guides/Si47xxEVB.pdf">Si4713 Evaluation Board Guide</a></p>
</fieldset>
<!-- last div intentionally skipped to fix footer background -->
