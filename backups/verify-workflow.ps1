$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Net.Http
$client=New-Object System.Net.Http.HttpClient
$client.Timeout=[TimeSpan]::FromSeconds(20)
$run=[Guid]::NewGuid().ToString()
$responses=New-Object 'System.Collections.Generic.List[object]'
$artifact=Join-Path $PSScriptRoot ('workflow-'+$run+'.json')
function Call-Api($method,$path,$payload=$null,$key=$null) {
    $message=New-Object System.Net.Http.HttpRequestMessage -ArgumentList ([System.Net.Http.HttpMethod]::new($method)),('http://127.0.0.1:18080'+$path)
    if($null -ne $payload) { $message.Content=New-Object System.Net.Http.StringContent -ArgumentList ($payload|ConvertTo-Json -Compress),([Text.Encoding]::UTF8),'application/json' }
    if($key) { [void]$message.Headers.TryAddWithoutValidation('Idempotency-Key',$key) }
    $result=$client.SendAsync($message).GetAwaiter().GetResult()
    $raw=$result.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    $record=[pscustomobject]@{method=$method;path=$path;status=[int]$result.StatusCode;body=($raw|ConvertFrom-Json)}
    $responses.Add($record)
    [pscustomobject]@{runId=$run;responses=$responses}|ConvertTo-Json -Depth 15|Set-Content -Encoding UTF8 $artifact
    Write-Host ('HTTP '+$record.status+' '+$method+' '+$path+' '+$raw)
    $result.Dispose();$message.Dispose()
    return $record
}
function Expect($record,$status) { if($record.status -ne $status) { throw "Unexpected HTTP status $($record.status), expected $status" } }
try {
    Expect (Call-Api GET '/actuator/health') 200
    $a=Call-Api POST '/api/v1/accounts' @{accountNumber=('WF-'+$run+'-A');currency='USD'};Expect $a 201
    $b=Call-Api POST '/api/v1/accounts' @{accountNumber=('WF-'+$run+'-B');currency='USD'};Expect $b 201
    $fundKey='workflow-'+$run+'-fund';$transferKey='workflow-'+$run+'-transfer'
    $fund=Call-Api POST "/api/v1/dev/accounts/$($a.body.id)/fund" @{amount=1000.00} $fundKey;Expect $fund 201
    $fundRetry=Call-Api POST "/api/v1/dev/accounts/$($a.body.id)/fund" @{amount=1000.00} $fundKey;Expect $fundRetry 200
    if(($fund.body|ConvertTo-Json -Compress) -ne ($fundRetry.body|ConvertTo-Json -Compress)) { throw 'Funding retry differs from original' }
    Expect (Call-Api POST "/api/v1/dev/accounts/$($a.body.id)/fund" @{amount=1001.00} $fundKey) 409
    $payload=@{sourceAccountId=$a.body.id;destinationAccountId=$b.body.id;amount=250.00}
    $transfer=Call-Api POST '/api/v1/transfers' $payload $transferKey;Expect $transfer 201
    $retry=Call-Api POST '/api/v1/transfers' $payload $transferKey;Expect $retry 200
    if(($transfer.body|ConvertTo-Json -Compress) -ne ($retry.body|ConvertTo-Json -Compress)) { throw 'Transfer retry differs from original' }
    Expect (Call-Api POST '/api/v1/transfers' @{sourceAccountId=$a.body.id;destinationAccountId=$b.body.id;amount=251.00} $transferKey) 409
    $finalA=Call-Api GET "/api/v1/accounts/$($a.body.id)";Expect $finalA 200
    $finalB=Call-Api GET "/api/v1/accounts/$($b.body.id)";Expect $finalB 200
    if([decimal]$finalA.body.balance -ne 750 -or [decimal]$finalB.body.balance -ne 250) { throw 'Customer balances do not match 750/250' }
    foreach($id in @($fund.body.id,$transfer.body.id)) {
        $details=Call-Api GET "/api/v1/transfers/$id";Expect $details 200
        if($details.body.status -ne 'COMPLETED') { throw 'Transfer not completed' }
    }
    $historyA=Call-Api GET "/api/v1/accounts/$($a.body.id)/transactions?page=0&size=20";Expect $historyA 200
    $historyB=Call-Api GET "/api/v1/accounts/$($b.body.id)/transactions?page=0&size=20";Expect $historyB 200
    if($historyA.body.totalElements -ne 2 -or $historyB.body.totalElements -ne 1) { throw 'Unexpected history counts' }
    if($historyA.body.transactions[0].transferId -ne $transfer.body.id -or $historyA.body.transactions[0].direction -ne 'OUTGOING' -or $historyA.body.transactions[1].transferId -ne $fund.body.id -or $historyA.body.transactions[1].direction -ne 'INCOMING') { throw 'First customer history is incorrect' }
    if($historyB.body.transactions[0].transferId -ne $transfer.body.id -or $historyB.body.transactions[0].direction -ne 'INCOMING') { throw 'Second customer history is incorrect' }
    $summary=[pscustomobject]@{runId=$run;accountA=$a.body;accountB=$b.body;fundingTransfer=$fund.body;customerTransfer=$transfer.body;finalA=$finalA.body;finalB=$finalB.body;fundKey=$fundKey;transferKey=$transferKey;responses=$responses;httpVerification='PASSED'}
    $summary|ConvertTo-Json -Depth 15|Set-Content -Encoding UTF8 $artifact
    Write-Host ('HTTP verification passed. Evidence: '+$artifact)
} finally { $client.Dispose() }
