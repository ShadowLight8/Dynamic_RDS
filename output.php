<div id="global" class="settings">

<h2>Transmitter Status</h2>
<?php exec("sudo i2cget -y 1 0x21 2>&1", $output, $return_val); ?>
<?php if (implode($output) != "Error: Read failed") : ?>
<div class='callout callout-success'>Detected QN8066 on I<sup>2</sup>C address 0x21</div>
<?php else: ?>
<div class='callout callout-danger'>Not detected on I<sup>2</sup>C addresses 0x21</div> <!-- TODO: Check on 0x11 as well -->
<?php endif; ?>

<?
PrintSettingGroup("DynRDSTransmitterType", "", "", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSPluginActivation", "", "Control when the transmitter will be active", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSTransmitterSettings", "", "", 1, "Dynamic_RDS");
?>
<?
PrintSettingGroup("DynRDSRDSSettings", "", "", 1, "Dynamic_RDS");
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
