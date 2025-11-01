# PowerShell script to test Lead Appointment Flow starting point messages
# Update $baseUrl with your server URL

$baseUrl = "http://localhost:8000"

# ============================================================
# 1. HAIR REGROWTH TREATMENTS
# ============================================================
$payload1 = @{
    object = "whatsapp_business_account"
    entry = @(
        @{
            id = "WHATSAPP_BUSINESS_ACCOUNT_ID"
            changes = @(
                @{
                    value = @{
                        messaging_product = "whatsapp"
                        metadata = @{
                            display_phone_number = "917729992376"
                            phone_number_id = "367633743092037"
                        }
                        contacts = @(
                            @{
                                profile = @{
                                    name = "Test User"
                                }
                                wa_id = "919876543210"
                            }
                        )
                        messages = @(
                            @{
                                from = "919876543210"
                                id = "wamid.test123456789"
                                timestamp = [int][double]::Parse((Get-Date -UFormat %s))
                                type = "text"
                                text = @{
                                    body = "Hi! I saw your ad for Oliva's Hair Regrowth treatments and want to know more."
                                }
                            }
                        )
                    }
                    field = "messages"
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "$baseUrl/ws/webhook" -Method Post -Body $payload1 -ContentType "application/json"

Write-Host "`n---`n" -ForegroundColor Green

# ============================================================
# 2. PRECISION+ LASER HAIR REDUCTION
# ============================================================
$payload2 = @{
    object = "whatsapp_business_account"
    entry = @(
        @{
            id = "WHATSAPP_BUSINESS_ACCOUNT_ID"
            changes = @(
                @{
                    value = @{
                        messaging_product = "whatsapp"
                        metadata = @{
                            display_phone_number = "917729992376"
                            phone_number_id = "367633743092037"
                        }
                        contacts = @(
                            @{
                                profile = @{
                                    name = "Test User"
                                }
                                wa_id = "919876543211"
                            }
                        )
                        messages = @(
                            @{
                                from = "919876543211"
                                id = "wamid.test123456790"
                                timestamp = [int][double]::Parse((Get-Date -UFormat %s))
                                type = "text"
                                text = @{
                                    body = "Hi! I saw your ad for Oliva's Precision+ Laser Hair Reduction and want to know more."
                                }
                            }
                        )
                    }
                    field = "messages"
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "$baseUrl/ws/webhook" -Method Post -Body $payload2 -ContentType "application/json"

Write-Host "`n---`n" -ForegroundColor Green

# ============================================================
# 3. SKIN BRIGHTENING TREATMENTS
# ============================================================
$payload3 = @{
    object = "whatsapp_business_account"
    entry = @(
        @{
            id = "WHATSAPP_BUSINESS_ACCOUNT_ID"
            changes = @(
                @{
                    value = @{
                        messaging_product = "whatsapp"
                        metadata = @{
                            display_phone_number = "917729992376"
                            phone_number_id = "367633743092037"
                        }
                        contacts = @(
                            @{
                                profile = @{
                                    name = "Test User"
                                }
                                wa_id = "919876543212"
                            }
                        )
                        messages = @(
                            @{
                                from = "919876543212"
                                id = "wamid.test123456791"
                                timestamp = [int][double]::Parse((Get-Date -UFormat %s))
                                type = "text"
                                text = @{
                                    body = "Hi! I saw your ad for Oliva's Skin Brightening treatments and want to know more."
                                }
                            }
                        )
                    }
                    field = "messages"
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "$baseUrl/ws/webhook" -Method Post -Body $payload3 -ContentType "application/json"

Write-Host "`n---`n" -ForegroundColor Green

# ============================================================
# 4. ACNE & SCAR TREATMENTS
# ============================================================
$payload4 = @{
    object = "whatsapp_business_account"
    entry = @(
        @{
            id = "WHATSAPP_BUSINESS_ACCOUNT_ID"
            changes = @(
                @{
                    value = @{
                        messaging_product = "whatsapp"
                        metadata = @{
                            display_phone_number = "917729992376"
                            phone_number_id = "367633743092037"
                        }
                        contacts = @(
                            @{
                                profile = @{
                                    name = "Test User"
                                }
                                wa_id = "919876543213"
                            }
                        )
                        messages = @(
                            @{
                                from = "919876543213"
                                id = "wamid.test123456792"
                                timestamp = [int][double]::Parse((Get-Date -UFormat %s))
                                type = "text"
                                text = @{
                                    body = "Hi! I saw your ad for Oliva's acne & scar treatments and want to know more."
                                }
                            }
                        )
                    }
                    field = "messages"
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "$baseUrl/ws/webhook" -Method Post -Body $payload4 -ContentType "application/json"

Write-Host "`n---`n" -ForegroundColor Green

# ============================================================
# 5. SKIN BOOSTERS
# ============================================================
$payload5 = @{
    object = "whatsapp_business_account"
    entry = @(
        @{
            id = "WHATSAPP_BUSINESS_ACCOUNT_ID"
            changes = @(
                @{
                    value = @{
                        messaging_product = "whatsapp"
                        metadata = @{
                            display_phone_number = "917729992376"
                            phone_number_id = "367633743092037"
                        }
                        contacts = @(
                            @{
                                profile = @{
                                    name = "Test User"
                                }
                                wa_id = "919876543214"
                            }
                        )
                        messages = @(
                            @{
                                from = "919876543214"
                                id = "wamid.test123456793"
                                timestamp = [int][double]::Parse((Get-Date -UFormat %s))
                                type = "text"
                                text = @{
                                    body = "Hi! I saw your ad for Oliva's Skin Boosters and want to know more."
                                }
                            }
                        )
                    }
                    field = "messages"
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri "$baseUrl/ws/webhook" -Method Post -Body $payload5 -ContentType "application/json"

