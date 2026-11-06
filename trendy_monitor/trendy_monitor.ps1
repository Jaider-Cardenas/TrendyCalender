param(
    [switch]$Once = $false
)

$CatalogUrls = @(
    'https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=0&_to=49',
    'https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=50&_to=99',
    'https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=100&_to=149',
    'https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=150&_to=199',
    'https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=200&_to=249',
    'https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?_from=250&_to=299'
)

$Product1016DirectUrl = 'https://www.maquillajetrendyshop.com/api/catalog_system/pub/products/search?fq=productId:1016'

$Keywords = @(
    'adviento',
    'calendario de adviento',
    'calendario adviento',
    'calendario-adviento',
    'wonderland',
    'calendario de adviento wonderland'
)

$TargetProductId = '1016'
$TargetProductNameKeyword = 'unidad de prueba ecommerce'
$CheckIntervalSeconds = 1800

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StateFile = Join-Path $ScriptDir 'trendy_state.json'
$LogFile   = Join-Path $ScriptDir 'trendy_monitor.log'
$AlertsFile = Join-Path $ScriptDir 'alertas_trendy.txt'

$Headers = @{
    'User-Agent' = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    'Accept' = 'application/json, text/plain, */*'
    'Accept-Language' = 'es-ES,es;q=0.9,en;q=0.8'
}

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $timestamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $formatted = "[$timestamp] $Level`: $Message"
    Write-Output $formatted
    Add-Content -Path $LogFile -Value $formatted -Encoding utf8
}

function Write-AlertFile {
    param([string]$AlertType, [string[]]$Lines)
    $timestamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    $divider = ('=' * 80)
    $subDivider = ('-' * 80)
    
    $content = @()
    $content += $divider
    $content += "FECHA Y HORA: $timestamp"
    $content += "TIPO DE ALERTA: $AlertType"
    $content += $subDivider
    $content += $Lines
    $content += $divider
    $content += ''
    
    Add-Content -Path $AlertsFile -Value ($content -join "`r`n") -Encoding utf8
    Write-Log "Alerta registrada en alertas_trendy.txt."
}

function Load-State {
    if (Test-Path $StateFile) {
        try {
            $raw = Get-Content $StateFile -Raw -Encoding utf8
            return ($raw | ConvertFrom-Json)
        } catch {
            Write-Log 'No se pudo leer archivo de estado, iniciando nuevo.' 'WARN'
        }
    }
    return [PSCustomObject]@{
        known_catalog_product_ids = @()
        known_keyword_product_ids = @()
        product_1016_snapshot = $null
        is_baseline_established = $false
        last_run = $null
    }
}

function Save-State($state) {
    try {
        $json = $state | ConvertTo-Json -Depth 6
        Set-Content -Path $StateFile -Value $json -Encoding utf8
    } catch {
        Write-Log "Error al guardar estado: $_" 'ERROR'
    }
}

function Matches-Keywords($product) {
    $name = ('' + $product.productName).ToLower()
    $title = ('' + $product.productTitle).ToLower()
    $full = "$name $title"
    
    $matched = @()
    foreach ($kw in $Keywords) {
        if ($full.Contains($kw.ToLower())) {
            $matched += $kw
        }
    }
    return $matched
}

function Get-ProductSummary($p) {
    $prodId = [string]$p.productId
    $name = [string]$p.productName
    $link = if ($p.link) { $p.link } else { "https://www.maquillajetrendyshop.com/$($p.linkText)/p" }
    
    $firstItem = if ($p.items -and $p.items.Count -gt 0) { $p.items[0] } else { $null }
    $firstSeller = if ($firstItem -and $firstItem.sellers -and $firstItem.sellers.Count -gt 0) { $firstItem.sellers[0] } else { $null }
    $offer = if ($firstSeller) { $firstSeller.commertialOffer } else { $null }
    
    $price = if ($offer -and $offer.Price -ne $null) { $offer.Price } else { 'N/A' }
    $stock = if ($offer -and $offer.AvailableQuantity -ne $null) { $offer.AvailableQuantity } else { 'N/A' }
    $available = if ($offer -and $offer.IsAvailable -ne $null) { $offer.IsAvailable } else { 'N/A' }
    
    return [PSCustomObject]@{
        Id = $prodId
        Name = $name
        Link = $link
        Price = $price
        Stock = $stock
        Available = $available
    }
}

function Run-MonitoringCycle {
    $nowStr = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Write-Log ('=' * 75)
    Write-Log "INICIANDO REVISION COMPLETA DEL CATALOGO TRENDY SHOP - $nowStr"
    Write-Log "Revisando $($CatalogUrls.Count) bloques de productos [0 al 299]..."
    Write-Log ('=' * 75)

    $state = Load-State
    $knownCatalogIds = [System.Collections.Generic.HashSet[string]]::new()
    if ($state.known_catalog_product_ids) {
        foreach ($id in $state.known_catalog_product_ids) { [void]$knownCatalogIds.Add([string]$id) }
    }

    $knownKeywordIds = [System.Collections.Generic.HashSet[string]]::new()
    if ($state.known_keyword_product_ids) {
        foreach ($id in $state.known_keyword_product_ids) { [void]$knownKeywordIds.Add([string]$id) }
    }

    $old1016 = $state.product_1016_snapshot
    $isBaseline = [bool]$state.is_baseline_established

    $allCurrentProducts = [System.Collections.Generic.Dictionary[string, Object]]::new()
    $totalFetched = 0

    # 1. Consultar todos los 6 bloques
    for ($i = 0; $i -lt $CatalogUrls.Count; $i++) {
        $url = $CatalogUrls[$i]
        try {
            Write-Log "[$($i + 1)/$($CatalogUrls.Count)] Consultando: $url"
            $batch = Invoke-RestMethod -Uri $url -Headers $Headers -Method Get
            if ($batch) {
                $totalFetched += $batch.Count
                foreach ($p in $batch) {
                    $itemPid = [string]$p.productId
                    if ($itemPid -and -not $allCurrentProducts.ContainsKey($itemPid)) {
                        $allCurrentProducts[$itemPid] = $p
                    }
                }
            }
        } catch {
            Write-Log "Error en bloque $($i + 1): $_" 'ERROR'
        }
        Start-Sleep -Milliseconds 400
    }

    Write-Log "Total recibidos: $totalFetched | Productos unicos consolidados: $($allCurrentProducts.Count)"

    # 2. Analizar productos
    $matchingKeywords = @()
    $newKeywordProducts = @()
    $newlyAddedCatalog = @()
    $product1016Found = $null

    foreach ($entry in $allCurrentProducts.GetEnumerator()) {
        $itemPid = $entry.Key
        $p = $entry.Value
        $summary = Get-ProductSummary $p
        $pname = $summary.Name.ToLower()

        if ($itemPid -eq $TargetProductId -or $pname.Contains($TargetProductNameKeyword)) {
            $product1016Found = $p
        }

        $matchedKws = Matches-Keywords $p
        if ($matchedKws.Count -gt 0) {
            $matchingKeywords += [PSCustomObject]@{ Product = $p; Keywords = $matchedKws; Summary = $summary }
            if (-not $knownKeywordIds.Contains($itemPid)) {
                $newKeywordProducts += [PSCustomObject]@{ Product = $p; Keywords = $matchedKws; Summary = $summary }
                [void]$knownKeywordIds.Add($itemPid)
            }
        }

        if ($isBaseline -and -not $knownCatalogIds.Contains($itemPid)) {
            $newlyAddedCatalog += [PSCustomObject]@{ Product = $p; Summary = $summary }
            [void]$knownCatalogIds.Add($itemPid)
        }
    }

    # 3. ENUMERAR CADA 30 MINUTOS EN CONSOLA
    Write-Output ''
    Write-Output ('-' * 75)
    Write-Output "LISTADO DE PRODUCTOS COINCIDENTES EN ESTE CICLO ('adviento' / 'wonderland'):"
    Write-Output "Total encontrados en los 6 bloques: $($matchingKeywords.Count)"
    Write-Output ('-' * 75)
    if ($matchingKeywords.Count -gt 0) {
        $idx = 1
        foreach ($item in $matchingKeywords) {
            $s = $item.Summary
            Write-Output "  [$idx] ID: $($s.Id) | Nombre: $($s.Name)"
            Write-Output "      Precio: `$$($s.Price) | Stock: $($s.Stock) | Disponible: $($s.Available)"
            Write-Output "      Palabras detectadas: $($item.Keywords -join ', ')"
            Write-Output "      Enlace: $($s.Link)"
            $idx++
        }
    } else {
        Write-Output "  (Ningun producto en los rangos 0..299 contiene 'adviento' o 'wonderland')"
    }
    Write-Output ('-' * 75)
    Write-Output ''

    # 4. LINEA BASE
    if (-not $isBaseline) {
        foreach ($k in $allCurrentProducts.Keys) {
            [void]$knownCatalogIds.Add($k)
        }
        $state.is_baseline_established = $true
        Write-Log "Linea base registrada: $($knownCatalogIds.Count) productos almacenados."

        $initLines = @(
            'Inicio formal del monitoreo de catalogo en 6 bloques [0 a 299].',
            "Total de productos en el catalogo inicial: $($knownCatalogIds.Count) productos registrados.",
            "Productos con palabras clave detectados inicialmente: $($matchingKeywords.Count)."
        )
        if ($matchingKeywords.Count -gt 0) {
            $initLines += ''
            $initLines += "Productos existentes con 'adviento' o 'wonderland':"
            foreach ($item in $matchingKeywords) {
                $s = $item.Summary
                $initLines += "  * ID $($s.Id): $($s.Name) (Precio: `$$($s.Price), Stock: $($s.Stock))"
            }
        }
        Write-AlertFile 'INICIO DE MONITOREO Y LINEA BASE' $initLines
    }

    # 5. ALERTA: NUEVOS PRODUCTOS AGREGADOS AL CATALOGO
    if ($newlyAddedCatalog.Count -gt 0) {
        $alertLines = @("Se detectaron $($newlyAddedCatalog.Count) NUEVOS productos agregados al catalogo:")
        $alertLines += ''
        foreach ($item in $newlyAddedCatalog) {
            $s = $item.Summary
            $matched = Matches-Keywords $item.Product
            $kwNote = if ($matched.Count -gt 0) { " [COINCIDE CON: $($matched -join ', ')]" } else { '' }
            $alertLines += "* ID: $($s.Id) | Nombre: $($s.Name)$kwNote"
            $alertLines += "  Precio: `$$($s.Price) | Stock: $($s.Stock) | Disponible: $($s.Available)"
            $alertLines += "  Enlace: $($s.Link)"
            $alertLines += ''
        }
        Write-Log 'NUEVOS PRODUCTOS DETECTADOS EN EL CATALOGO!' 'WARN'
        Write-AlertFile 'NUEVO(S) PRODUCTO(S) AGREGADO(S) AL CATALOGO' $alertLines
    }

    # 6. ALERTA: NUEVO PRODUCTO CON PALABRAS CLAVE
    if ($newKeywordProducts.Count -gt 0 -and $newlyAddedCatalog.Count -eq 0) {
        $kwLines = @("Se detectaron $($newKeywordProducts.Count) producto(s) nuevos con palabras clave de Adviento / Wonderland:")
        $kwLines += ''
        foreach ($item in $newKeywordProducts) {
            $s = $item.Summary
            $kwLines += "* ID: $($s.Id) | Nombre: $($s.Name)"
            $kwLines += "  Palabras clave: $($item.Keywords -join ', ')"
            $kwLines += "  Precio: `$$($s.Price) | Stock: $($s.Stock)"
            $kwLines += "  Enlace: $($s.Link)"
            $kwLines += ''
        }
        Write-Log 'NUEVO PRODUCTO DE ADVIENTO/WONDERLAND DETECTADO!' 'WARN'
        Write-AlertFile 'NUEVO PRODUCTO DE ADVIENTO / WONDERLAND DETECTADO' $kwLines
    }

    # 7. PRODUCTO 1016
    if (-not $product1016Found) {
        try {
            $resDirect = Invoke-RestMethod -Uri $Product1016DirectUrl -Headers $Headers -Method Get
            if ($resDirect -and $resDirect.Count -gt 0) {
                $product1016Found = $resDirect[0]
                Write-Log 'Producto 1016 consultado mediante endpoint directo (no estaba en el rango 0..299).'
            }
        } catch {
            Write-Log "Error consultando producto 1016 directamente: $_" 'WARN'
        }
    }

    if ($product1016Found) {
        $s1016 = Get-ProductSummary $product1016Found
        $currentSnapshot = [PSCustomObject]@{
            Price = $s1016.Price
            Stock = $s1016.Stock
            Available = $s1016.Available
            Name = $s1016.Name
        }

        if (-not $old1016) {
            Write-Log "Primer registro guardado para Producto 1016 ('$($s1016.Name)')."
            Write-Log "Valores iniciales: Precio=`$$($s1016.Price) | Stock=$($s1016.Stock) | Disponible=$($s1016.Available)"
            $state.product_1016_snapshot = $currentSnapshot
        } else {
            $diffs = @()
            if ($old1016.Price -ne $currentSnapshot.Price) {
                $diffs += "Precio cambio: '$($old1016.Price)' -> '$($currentSnapshot.Price)'"
            }
            if ($old1016.Stock -ne $currentSnapshot.Stock) {
                $diffs += "Stock cambio: '$($old1016.Stock)' -> '$($currentSnapshot.Stock)'"
            }
            if ($old1016.Available -ne $currentSnapshot.Available) {
                $diffs += "Disponibilidad cambio: '$($old1016.Available)' -> '$($currentSnapshot.Available)'"
            }
            if ($old1016.Name -ne $currentSnapshot.Name) {
                $diffs += "Nombre cambio: '$($old1016.Name)' -> '$($currentSnapshot.Name)'"
            }

            if ($diffs.Count -gt 0) {
                $changeLines = @(
                    "El producto de control ID $TargetProductId ('$($s1016.Name)') fue modificado.",
                    "Resumen actual: Precio=`$$($s1016.Price) | Stock=$($s1016.Stock) | Disponible=$($s1016.Available)",
                    "Enlace: $($s1016.Link)",
                    '',
                    'Parametros modificados detectados:'
                )
                foreach ($d in $diffs) {
                    $changeLines += "  * $d"
                }
                Write-Log 'CAMBIOS DETECTADOS EN PRODUCTO 1016!' 'WARN'
                Write-AlertFile 'PRODUCTO 1016 MODIFICADO (Unidad De Prueba Ecommerce)' $changeLines
                $state.product_1016_snapshot = $currentSnapshot
            } else {
                Write-Log "Producto 1016 sin modificaciones (Precio: `$$($s1016.Price), Stock: $($s1016.Stock), Disponible: $($s1016.Available))."
            }
        }
    } else {
        Write-Log 'No fue posible obtener datos del Producto 1016.' 'WARN'
    }

    # 8. GUARDAR ESTADO
    $state.known_catalog_product_ids = @($knownCatalogIds)
    $state.known_keyword_product_ids = @($knownKeywordIds)
    $state.last_run = $nowStr
    Save-State $state
    Write-Log 'Fin de la revision. Catalogo y estado guardados con exito.'
}

if ($Once) {
    Run-MonitoringCycle
} else {
    Write-Log 'Iniciando Trendy Shop Monitor en modo continuo (cada 30 minutos).'
    Write-Log "Archivo de alertas: $AlertsFile"
    Write-Log 'Presiona Ctrl + C para detener.'
    while ($true) {
        Run-MonitoringCycle
        Write-Log "Proxima revision en 30 minutos ($CheckIntervalSeconds seg). En espera..."
        Start-Sleep -Seconds $CheckIntervalSeconds
    }
}
