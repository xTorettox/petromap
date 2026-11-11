<?php
/**
 * SullApps Wrapper - PetroMaps (Visor GIS / Áreas Hidrocarburíferas Vaca Muerta)
 */
require_once __DIR__ . '/../../auth.php';
$currentAppName = 'PetroMaps';
$currentAppSlug = 'petromaps';
$defaultSubdomain = 'petromap';
requireAppAccess($currentAppSlug);
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover">
    <meta name="theme-color" content="#006837">
    <title>PetroMaps | SullApps Suite</title>
    <link rel="icon" type="image/png" href="/img/favicon.png">
    <link rel="stylesheet" href="/assets/sullapps.css">
</head>
<body class="sullapps-wrapper-body">
    <?php
    include __DIR__ . '/../../shared/topbar.php';
    $embedUrl = resolveSullAppEmbedUrl($currentAppSlug, $defaultSubdomain, ['petromaps', 'petromap', 'áreas', 'areas', 'mapa', 'vaca muerta']);
    ?>
    <div class="sullapps-iframe-container">
        <iframe
            class="sullapps-iframe"
            src="<?= htmlspecialchars($embedUrl, ENT_QUOTES, 'UTF-8'); ?>"
            width="100%"
            height="calc(100vh - 48px)"
            frameborder="0"
            allow="clipboard-write"
            title="PetroMaps - Sullair Argentina"
            loading="eager">
        </iframe>
    </div>
</body>
</html>
