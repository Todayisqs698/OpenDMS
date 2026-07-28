Start-Process -FilePath "D:\anaconda\envs\py311\python.exe" -ArgumentList "-m","uvicorn","backend.main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory "C:\Users\SQS\Desktop\edgeguard" -WindowStyle Minimized
Start-Sleep -Seconds 3
Start-Process -FilePath "cmd" -ArgumentList "/c","cd /d C:\Users\SQS\Desktop\edgeguard\frontend && npm run dev" -WorkingDirectory "C:\Users\SQS\Desktop\edgeguard\frontend" -WindowStyle Minimized
Write-Host "Backend: http://localhost:8000"
Write-Host "Frontend: http://localhost:8005"
