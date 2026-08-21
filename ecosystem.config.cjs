module.exports = {
  apps: [
    {
      name: "telegram-workspace-manager",
      cwd: "/opt/telegram-workspace-manager",
      script: ".venv/bin/python",
      args: "-m app.telegram.bot",
      interpreter: "none",
      autorestart: true,
      restart_delay: 5000,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
