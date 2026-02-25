param(
    [string]$CertDir = "$(Join-Path $PSScriptRoot '..\certs')",
    [int]$Days = 3650
)

$ErrorActionPreference = 'Stop'

function New-DevCertificate {
    param(
        [string]$Name,
        [string]$TargetDir,
        [int]$ValidDays
    )

    $keyFile = Join-Path $TargetDir "$Name.key"
    $csrFile = Join-Path $TargetDir "$Name.csr"
    $crtFile = Join-Path $TargetDir "$Name.crt"
    $caFile = Join-Path $TargetDir "ca.crt"
    $caKeyFile = Join-Path $TargetDir "ca.key"
    $extFile = Join-Path $TargetDir "$Name.ext"

    & openssl genrsa -out $keyFile 2048 | Out-Null
    & openssl req -new -key $keyFile -out $csrFile -subj "/C=CN/ST=Beijing/L=Beijing/O=ACPs-Demo/OU=Dev/CN=$Name" | Out-Null
@"
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth,clientAuth
subjectAltName=DNS:$Name,DNS:localhost,IP:127.0.0.1
"@ | Set-Content -Path $extFile -Encoding ascii
    & openssl x509 -req -in $csrFile -CA $caFile -CAkey $caKeyFile -CAcreateserial -out $crtFile -days $ValidDays -sha256 -extfile $extFile | Out-Null
    Remove-Item -Force $csrFile
    Remove-Item -Force $extFile

    Write-Host "[mTLS] issued cert for $Name"
}

$resolvedCertDir = Resolve-Path -Path (New-Item -ItemType Directory -Path $CertDir -Force)
$certPath = $resolvedCertDir.Path

$opensslConf = Join-Path $certPath "openssl.cnf"
if (-not (Test-Path $opensslConf)) {
@"
[ req ]
default_bits = 2048
distinguished_name = req_distinguished_name
prompt = no

[ req_distinguished_name ]
C = CN
ST = Beijing
L = Beijing
O = ACPs-Demo
OU = Dev
CN = localhost
"@ | Set-Content -Path $opensslConf -Encoding utf8
}

$env:OPENSSL_CONF = $opensslConf

Write-Host "[mTLS] generating dev CA in $certPath"
$caKey = Join-Path $certPath "ca.key"
$caCrt = Join-Path $certPath "ca.crt"

& openssl genrsa -out $caKey 4096 | Out-Null
& openssl req -x509 -new -nodes -key $caKey -sha256 -days $Days -out $caCrt -subj "/C=CN/ST=Beijing/L=Beijing/O=ACPs-Demo/OU=Dev/CN=acps-dev-ca" -addext "basicConstraints=critical,CA:TRUE,pathlen:0" -addext "keyUsage=critical,keyCertSign,cRLSign" -addext "subjectKeyIdentifier=hash" | Out-Null

# AIC-based names (used by fallback resolver)
New-DevCertificate -Name "reading_concierge_001" -TargetDir $certPath -ValidDays $Days
New-DevCertificate -Name "reader_profile_agent_001" -TargetDir $certPath -ValidDays $Days
New-DevCertificate -Name "book_content_agent_001" -TargetDir $certPath -ValidDays $Days
New-DevCertificate -Name "rec_ranking_agent_001" -TargetDir $certPath -ValidDays $Days

# Explicit mtls-path names used in config.example.json
New-DevCertificate -Name "reader_profile" -TargetDir $certPath -ValidDays $Days
New-DevCertificate -Name "book_content" -TargetDir $certPath -ValidDays $Days
New-DevCertificate -Name "rec_ranking" -TargetDir $certPath -ValidDays $Days

Write-Host "[mTLS] done. certs generated in $certPath"
