import { useEffect, useRef } from "react";

export default function QuantumBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const mouse = { x: 0, y: 0, targetX: 0, targetY: 0 };
    let gridOffset = 0;

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    const handleMouseMove = (e: MouseEvent) => {
      mouse.targetX = (e.clientX / width - 0.5) * 40;
      mouse.targetY = (e.clientY / height - 0.5) * 40;
    };

    window.addEventListener("resize", handleResize);
    window.addEventListener("mousemove", handleMouseMove);

    // Particles setup
    const particleCount = 65;
    const particles = Array.from({ length: particleCount }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      size: Math.random() * 2 + 0.6,
      speedY: -(Math.random() * 0.4 + 0.15),
      speedX: (Math.random() - 0.5) * 0.25,
      colorType: Math.random() > 0.35 ? ("cyan" as const) : ("magenta" as const),
      baseAlpha: Math.random() * 0.6 + 0.2,
      pulseSpeed: Math.random() * 0.03 + 0.01,
      pulseOffset: Math.random() * Math.PI * 2,
    }));

    const render = (time: number) => {
      mouse.x += (mouse.targetX - mouse.x) * 0.05;
      mouse.y += (mouse.targetY - mouse.y) * 0.05;

      ctx.clearRect(0, 0, width, height);

      // 1. Perspective Wireframe Grid
      const horizon = height * 0.52;
      const depth = height - horizon;

      if (depth > 0) {
        ctx.save();
        gridOffset = (gridOffset + 0.25) % 40;

        const maskGrad = ctx.createLinearGradient(0, horizon, 0, height);
        maskGrad.addColorStop(0, "rgba(0, 210, 255, 0)");
        maskGrad.addColorStop(0.2, "rgba(0, 210, 255, 0.05)");
        maskGrad.addColorStop(0.7, "rgba(0, 210, 255, 0.13)");
        maskGrad.addColorStop(1, "rgba(155, 81, 224, 0.18)");

        ctx.strokeStyle = maskGrad;
        ctx.lineWidth = 1;

        const numHorizontal = 18;
        for (let i = 0; i <= numHorizontal; i++) {
          const p = Math.pow(i / numHorizontal, 2.2);
          const y = horizon + p * depth + gridOffset * 0.4 * p;
          if (y > height) continue;

          ctx.beginPath();
          const curve = Math.sin(((y - horizon) / depth) * Math.PI) * 25 * (mouse.x * 0.02);
          ctx.moveTo(0, y);
          ctx.quadraticCurveTo(width / 2 + mouse.x, y + curve, width, y);
          ctx.stroke();
        }

        const numVertical = 26;
        const centerX = width / 2 + mouse.x * 0.5;
        for (let i = -numVertical / 2; i <= numVertical / 2; i++) {
          const bottomX = centerX + i * 90 * (1 + Math.abs(i) * 0.08);
          ctx.beginPath();
          ctx.moveTo(centerX, horizon);
          ctx.lineTo(bottomX, height);
          ctx.stroke();
        }
        ctx.restore();
      }

      // 2. Floating Stardust Particles
      for (const p of particles) {
        p.y += p.speedY;
        p.x += p.speedX;

        if (p.y < -10) {
          p.y = height + 10;
          p.x = Math.random() * width;
        }
        if (p.x < -10) p.x = width + 10;
        if (p.x > width + 10) p.x = -10;

        const alpha = p.baseAlpha + Math.sin(time * 0.001 * p.pulseSpeed * 60 + p.pulseOffset) * 0.25;
        const clampedAlpha = Math.max(0.05, Math.min(0.9, alpha));

        ctx.save();
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);

        if (p.colorType === "cyan") {
          ctx.fillStyle = `rgba(0, 210, 255, ${clampedAlpha})`;
          ctx.shadowColor = "rgba(0, 210, 255, 0.8)";
        } else {
          ctx.fillStyle = `rgba(217, 70, 239, ${clampedAlpha})`;
          ctx.shadowColor = "rgba(217, 70, 239, 0.8)";
        }

        ctx.shadowBlur = p.size > 1.5 ? 8 : 4;
        ctx.fill();
        ctx.restore();
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animId);
    };
  }, []);

  return (
    <div className="qos-bg-stage">
      <canvas ref={canvasRef} className="qos-bg-canvas" />
      <div className="qos-ambient-orb qos-ambient-orb--cyan" />
      <div className="qos-ambient-orb qos-ambient-orb--magenta" />
    </div>
  );
}
