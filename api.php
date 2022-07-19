<?

function getEndpointsDynamic_RDS() {
    $result = array();

    $ep = array(
        'method' => 'GET',
        'endpoint' => 'FastUpdate',
        'callback' => 'DynRDSFastUpdate');

    array_push($result, $ep);

    return $result;
}

function DynRDSFastUpdate() {
    shell_exec(escapeshellcmd("sudo /home/fpp/media/plugins/Dynamic_RDS/callbacks.py --update"));

    $result = array();
    $result['version'] = 'Dynamic RDS 1.0.0';

    return json($result);
}
?>
