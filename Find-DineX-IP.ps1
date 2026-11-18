$client = New-Object System.Net.Sockets.UdpClient
try {
    $client.Connect("8.8.8.8", 80)
    $address = $client.Client.LocalEndPoint.Address.IPAddressToString
    if ($address -and $address -ne "0.0.0.0" -and $address -notlike "169.254*") {
        Write-Output $address
    }
}
finally {
    $client.Dispose()
}
