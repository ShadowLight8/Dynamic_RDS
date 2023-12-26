<?

function getEndpointsDynamic_RDS() {
    $result = array();

    $ep = array(
        'method' => 'GET', 'endpoint' => 'FastUpdate', 'callback' => 'DynRDSFastUpdate',
        'method' => 'POST', 'endpoint' => 'PiBootChange/:Change', 'callback' => 'DynRDSPiBootChange'
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
    $value = file_get_contents('php://input');
    $change = params('Change');

    shell_exec("echo " . $value . "> ~/test.txt");
    shell_exec("echo " . $change . ">> ~/test.txt");

    switch ($change) {
        case 'SoftwareI2C':
           break;
    }
}
?>
