@echo off
echo Starting WeatherAlpha tunnel via localhost.run...
ssh -i "C:\Users\zedwa\.ssh\localhost_run_key" -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:localhost:3001 localhost.run
pause
