# Prints the URL other devices should use, and checks the firewall is open.
# Streamlit's own "Network URL" is unreliable on machines with a corporate VPN --
# it often advertises the VPN adapter, which other devices cannot route to.

$Port = 8501

Write-Host "`nCandidate addresses for other devices" -ForegroundColor Cyan
Write-Host ("-" * 60)

$profiles = @{}
Get-NetConnectionProfile | ForEach-Object { $profiles[$_.InterfaceAlias] = $_ }

$candidates = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -ne "127.0.0.1" -and
        $_.IPAddress -notlike "169.254.*" -and   # link-local, no real network
        $_.PrefixLength -lt 32                    # /32 means VPN single-host route
    }

if (-not $candidates) {
    Write-Host "No routable LAN address found. Are you on WiFi?" -ForegroundColor Red
}

foreach ($ip in $candidates) {
    $p = $profiles[$ip.InterfaceAlias]
    $net = if ($p) { $p.Name } else { "unknown network" }
    $cat = if ($p) { $p.NetworkCategory } else { "?" }
    Write-Host ""
    Write-Host ("  http://{0}:{1}" -f $ip.IPAddress, $Port) -ForegroundColor Green
    Write-Host ("     network : {0}  ({1}, /{2})" -f $net, $cat, $ip.PrefixLength) -ForegroundColor DarkGray
    if ($cat -eq "DomainAuthenticated") {
        Write-Host "     note    : corporate network - may block device-to-device traffic" -ForegroundColor Yellow
    }
}

Write-Host "`nFirewall" -ForegroundColor Cyan
Write-Host ("-" * 60)
$rule = Get-NetFirewallRule -DisplayName "Streamlit Conference Intel $Port" -ErrorAction SilentlyContinue
if ($rule -and $rule.Enabled -eq "True") {
    Write-Host "  Inbound TCP $Port is allowed." -ForegroundColor Green
} else {
    Write-Host "  No allow rule for port $Port. Run this in an ADMIN PowerShell:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  New-NetFirewallRule -DisplayName 'Streamlit Conference Intel $Port' ``" -ForegroundColor White
    Write-Host "    -Direction Inbound -Protocol TCP -LocalPort $Port ``" -ForegroundColor White
    Write-Host "    -Action Allow -Profile Private,Public" -ForegroundColor White
}

$listening = (netstat -ano | Select-String ":$Port\s+.*LISTENING") -ne $null
Write-Host "`nApp status" -ForegroundColor Cyan
Write-Host ("-" * 60)
if ($listening) {
    Write-Host "  Streamlit is listening on port $Port." -ForegroundColor Green
} else {
    Write-Host "  Nothing is listening on port $Port. Start it with .\run.ps1" -ForegroundColor Red
}
Write-Host ""
