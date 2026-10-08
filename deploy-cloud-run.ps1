# Deploy the API to Cloud Run attached to Cloud SQL.
# Fill these, then: .\deploy-cloud-run.ps1

$Project = "footballplatform"
$Region = "us-east1"
$Service = "manager-desk"
$Instance = "pesdata"   # Cloud SQL instance name
$DbUser = "pesdata"
$DbName = "pesdata"

if (-not $env:DB_PASSWORD) {
    throw "Set DB_PASSWORD in the environment before deploying."
}

gcloud config set project $Project

gcloud sql instances describe $Instance --project $Project 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud sql instances create $Instance --database-version=POSTGRES_16 --cpu=1 --memory=4GiB --region=$Region --project=$Project
    gcloud sql databases create $DbName --instance=$Instance --project=$Project
    gcloud sql users create $DbUser --instance=$Instance --password=$env:DB_PASSWORD --project=$Project
}

$Connection = "${Project}:${Region}:${Instance}"
$Image = "gcr.io/${Project}/${Service}"

gcloud builds submit --tag $Image --project $Project

$oauth = @{}
Get-Content "data\google_oauth.env" | ForEach-Object {
    if ($_ -match "^\s*#" -or $_ -notmatch "=") { return }
    $k, $v = $_.Split("=", 2)
    $oauth[$k.Trim()] = $v.Trim()
}

gcloud run deploy $Service `
    --image $Image `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --add-cloudsql-instances $Connection `
    --set-env-vars "CLOUD_SQL_CONNECTION_NAME=$Connection,DB_USER=$DbUser,DB_NAME=$DbName,GOOGLE_CLIENT_ID=$($oauth.GOOGLE_CLIENT_ID),GOOGLE_CLIENT_SECRET=$($oauth.GOOGLE_CLIENT_SECRET),GOOGLE_APP_CLIENT_IDS=$($oauth.GOOGLE_APP_CLIENT_IDS)" `
    --set-env-vars "DB_PASSWORD=$($env:DB_PASSWORD)" `
    --project $Project

Write-Host "Point the Android app API URL at the Cloud Run service URL."
Write-Host "Add https://YOUR-SERVICE.run.app/auth/google/callback as an Authorized redirect URI."
