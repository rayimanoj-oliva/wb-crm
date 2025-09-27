# PowerShell script for testing prefill messages with curl
Write-Host "🧪 Curl Commands for Testing Prefill Messages" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

Write-Host ""
Write-Host "1️⃣ Test webhook with Banjara Hills referrer:" -ForegroundColor Yellow
Write-Host "--------------------------------------------" -ForegroundColor Yellow

$banjaraPayload = @{
    entry = @(
        @{
            changes = @(
                @{
                    value = @{
                        contacts = @(
                            @{
                                wa_id = "918309867004"
                                profile = @{
                                    name = "Banjara Hills User"
                                }
                            }
                        )
                        messages = @(
                            @{
                                from = "918309867004"
                                id = "banjara_test_123"
                                timestamp = "1758972000"
                                type = "text"
                                text = @{
                                    body = "Hi, I want to book an appointment. I came from banjara.olivaclinics.com"
                                }
                            }
                        )
                        metadata = @{
                            display_phone_number = "917729992376"
                        }
                    }
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/ws/webhook" -Method POST -Headers @{"Content-Type"="application/json"} -Body $banjaraPayload
    Write-Host "✅ Banjara Hills webhook: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Banjara Hills webhook failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "2️⃣ Test webhook with Jubilee Hills referrer:" -ForegroundColor Yellow
Write-Host "---------------------------------------------" -ForegroundColor Yellow

$jubileePayload = @{
    entry = @(
        @{
            changes = @(
                @{
                    value = @{
                        contacts = @(
                            @{
                                wa_id = "918309867005"
                                profile = @{
                                    name = "Jubilee Hills User"
                                }
                            }
                        )
                        messages = @(
                            @{
                                from = "918309867005"
                                id = "jubilee_test_123"
                                timestamp = "1758972000"
                                type = "text"
                                text = @{
                                    body = "Hello, I need to book an appointment at Jubilee Hills center"
                                }
                            }
                        )
                        metadata = @{
                            display_phone_number = "917729992376"
                        }
                    }
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/ws/webhook" -Method POST -Headers @{"Content-Type"="application/json"} -Body $jubileePayload
    Write-Host "✅ Jubilee Hills webhook: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ Jubilee Hills webhook failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "3️⃣ Test webhook with UTM parameters:" -ForegroundColor Yellow
Write-Host "-------------------------------------" -ForegroundColor Yellow

$utmPayload = @{
    entry = @(
        @{
            changes = @(
                @{
                    value = @{
                        contacts = @(
                            @{
                                wa_id = "918309867006"
                                profile = @{
                                    name = "UTM Test User"
                                }
                            }
                        )
                        messages = @(
                            @{
                                from = "918309867006"
                                id = "utm_test_123"
                                timestamp = "1758972000"
                                type = "text"
                                text = @{
                                    body = "utm_source=olivaclinics&utm_medium=website&utm_campaign=gachibowli&utm_content=hyderabad"
                                }
                            }
                        )
                        metadata = @{
                            display_phone_number = "917729992376"
                        }
                    }
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/ws/webhook" -Method POST -Headers @{"Content-Type"="application/json"} -Body $utmPayload
    Write-Host "✅ UTM webhook: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "❌ UTM webhook failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "4️⃣ Check referrer tracking for Banjara Hills:" -ForegroundColor Yellow
Write-Host "----------------------------------------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/referrer/918309867004" -Method GET -Headers @{"accept"="application/json"}
    Write-Host "✅ Banjara Hills referrer: $($response.StatusCode)" -ForegroundColor Green
    $data = $response.Content | ConvertFrom-Json
    Write-Host "   🏥 Center: $($data.center_name)" -ForegroundColor Cyan
    Write-Host "   📍 Location: $($data.location)" -ForegroundColor Cyan
} catch {
    Write-Host "❌ Banjara Hills referrer check failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "5️⃣ Check referrer tracking for Jubilee Hills:" -ForegroundColor Yellow
Write-Host "----------------------------------------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/referrer/918309867005" -Method GET -Headers @{"accept"="application/json"}
    Write-Host "✅ Jubilee Hills referrer: $($response.StatusCode)" -ForegroundColor Green
    $data = $response.Content | ConvertFrom-Json
    Write-Host "   🏥 Center: $($data.center_name)" -ForegroundColor Cyan
    Write-Host "   📍 Location: $($data.location)" -ForegroundColor Cyan
} catch {
    Write-Host "❌ Jubilee Hills referrer check failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "6️⃣ Check referrer tracking for UTM test:" -ForegroundColor Yellow
Write-Host "-----------------------------------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/referrer/918309867006" -Method GET -Headers @{"accept"="application/json"}
    Write-Host "✅ UTM referrer: $($response.StatusCode)" -ForegroundColor Green
    $data = $response.Content | ConvertFrom-Json
    Write-Host "   🏥 Center: $($data.center_name)" -ForegroundColor Cyan
    Write-Host "   📍 Location: $($data.location)" -ForegroundColor Cyan
} catch {
    Write-Host "❌ UTM referrer check failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "7️⃣ Get all referrer records:" -ForegroundColor Yellow
Write-Host "----------------------------" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/referrer/" -Method GET -Headers @{"accept"="application/json"}
    Write-Host "✅ All referrer records: $($response.StatusCode)" -ForegroundColor Green
    $data = $response.Content | ConvertFrom-Json
    Write-Host "   📊 Total records: $($data.Count)" -ForegroundColor Cyan
} catch {
    Write-Host "❌ All referrer records check failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "✅ Curl testing completed!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Expected Results:" -ForegroundColor Yellow
Write-Host "- Referrer tracking records should be created" -ForegroundColor White
Write-Host "- Center names should be captured correctly" -ForegroundColor White
Write-Host "- UTM parameters should be stored" -ForegroundColor White
Write-Host "- Appointment confirmations should include center info" -ForegroundColor White
