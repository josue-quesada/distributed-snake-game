"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface Position {
  x: number
  y: number
}

interface Direction {
  x: number
  y: number
}

export default function SnakeGame() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [snake, setSnake] = useState<Position[]>([{ x: 10, y: 10 }])
  const [direction, setDirection] = useState<Direction>({ x: 0, y: 0 })
  const [gameStarted, setGameStarted] = useState(false)
  const [lastKey, setLastKey] = useState<string>("")

  const GRID_SIZE = 20
  const CANVAS_SIZE = 400
  const GRID_COUNT = CANVAS_SIZE / GRID_SIZE

  // Función para dibujar el juego
  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Limpiar canvas
    ctx.fillStyle = "#0a0a0a"
    ctx.fillRect(0, 0, CANVAS_SIZE, CANVAS_SIZE)

    // Dibujar cuadrícula
    ctx.strokeStyle = "#1a1a1a"
    ctx.lineWidth = 1
    for (let i = 0; i <= GRID_COUNT; i++) {
      ctx.beginPath()
      ctx.moveTo(i * GRID_SIZE, 0)
      ctx.lineTo(i * GRID_SIZE, CANVAS_SIZE)
      ctx.stroke()

      ctx.beginPath()
      ctx.moveTo(0, i * GRID_SIZE)
      ctx.lineTo(CANVAS_SIZE, i * GRID_SIZE)
      ctx.stroke()
    }

    // Dibujar serpiente
    snake.forEach((segment, index) => {
      if (index === 0) {
        // Cabeza de la serpiente
        ctx.fillStyle = "#00ff41"
        ctx.shadowColor = "#00ff41"
        ctx.shadowBlur = 10
      } else {
        // Cuerpo de la serpiente
        ctx.fillStyle = "#00cc33"
        ctx.shadowBlur = 5
      }

      ctx.fillRect(segment.x * GRID_SIZE + 1, segment.y * GRID_SIZE + 1, GRID_SIZE - 2, GRID_SIZE - 2)
    })

    // Resetear sombra
    ctx.shadowBlur = 0
  }, [snake])

  // Función para mover la serpiente
  const moveSnake = useCallback(() => {
    if (direction.x === 0 && direction.y === 0) return

    setSnake((prevSnake) => {
      const newSnake = [...prevSnake]
      const head = { ...newSnake[0] }

      head.x += direction.x
      head.y += direction.y

      // Wrap around edges (opcional, puedes quitarlo si quieres que sea manejado por el backend)
      if (head.x < 0) head.x = GRID_COUNT - 1
      if (head.x >= GRID_COUNT) head.x = 0
      if (head.y < 0) head.y = GRID_COUNT - 1
      if (head.y >= GRID_COUNT) head.y = 0

      newSnake.unshift(head)
      newSnake.pop() // Mantener el tamaño constante por ahora

      return newSnake
    })
  }, [direction])

  // Manejar teclas
  const handleKeyPress = useCallback(
    (e: KeyboardEvent) => {
      let newDirection: Direction = { x: 0, y: 0 }
      let keyPressed = ""

      switch (e.key) {
        case "ArrowUp":
          newDirection = { x: 0, y: -1 }
          keyPressed = "↑"
          break
        case "ArrowDown":
          newDirection = { x: 0, y: 1 }
          keyPressed = "↓"
          break
        case "ArrowLeft":
          newDirection = { x: -1, y: 0 }
          keyPressed = "←"
          break
        case "ArrowRight":
          newDirection = { x: 1, y: 0 }
          keyPressed = "→"
          break
        default:
          return
      }

      // Prevenir movimiento opuesto (opcional)
      if (direction.x !== -newDirection.x || direction.y !== -newDirection.y) {
        setDirection(newDirection)
        setLastKey(keyPressed)
        setGameStarted(true)

        // Log para el backend distribuido
        console.log("🎮 Tecla presionada:", e.key, "| Dirección:", newDirection)
        console.log("📡 Evento para backend:", {
          key: e.key,
          direction: newDirection,
          timestamp: Date.now(),
        })
      }
    },
    [direction],
  )

  // Game loop
  useEffect(() => {
    const gameInterval = setInterval(() => {
      if (gameStarted) {
        moveSnake()
      }
    }, 150)

    return () => clearInterval(gameInterval)
  }, [gameStarted, moveSnake])

  // Dibujar en cada frame
  useEffect(() => {
    draw()
  }, [draw])

  // Event listeners
  useEffect(() => {
    window.addEventListener("keydown", handleKeyPress)
    return () => window.removeEventListener("keydown", handleKeyPress)
  }, [handleKeyPress])

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-black to-gray-900 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full space-y-6">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-bold text-green-400 font-mono tracking-wider">🐍 SNAKE VISUAL</h1>
          <p className="text-gray-400 text-sm">Frontend para Sistema Distribuido</p>
        </div>

        {/* Game Card */}
        <Card className="bg-gray-800/50 border-green-500/30 backdrop-blur">
          <CardHeader className="text-center pb-4">
            <CardTitle className="text-green-400 font-mono">Visualizador del Juego</CardTitle>
            <div className="flex justify-center gap-2 mt-2">
              <Badge variant="outline" className="text-green-400 border-green-400">
                {gameStarted ? "Jugando" : "Esperando..."}
              </Badge>
              {lastKey && (
                <Badge variant="outline" className="text-blue-400 border-blue-400">
                  Última tecla: {lastKey}
                </Badge>
              )}
            </div>
          </CardHeader>

          <CardContent className="flex flex-col items-center space-y-4">
            {/* Canvas */}
            <div className="relative">
              <canvas
                ref={canvasRef}
                width={CANVAS_SIZE}
                height={CANVAS_SIZE}
                className="border-2 border-green-500/50 rounded-lg shadow-lg shadow-green-500/20"
                style={{ imageRendering: "pixelated" }}
              />
              {!gameStarted && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50 rounded-lg">
                  <p className="text-green-400 font-mono text-lg animate-pulse">Presiona una flecha para comenzar</p>
                </div>
              )}
            </div>

            {/* Controls */}
            <div className="text-center space-y-2">
              <p className="text-gray-300 font-mono text-sm">Usa las flechas del teclado para mover la serpiente</p>
              <div className="flex justify-center gap-2 text-xs">
                <kbd className="px-2 py-1 bg-gray-700 rounded text-green-400">↑</kbd>
                <kbd className="px-2 py-1 bg-gray-700 rounded text-green-400">↓</kbd>
                <kbd className="px-2 py-1 bg-gray-700 rounded text-green-400">←</kbd>
                <kbd className="px-2 py-1 bg-gray-700 rounded text-green-400">→</kbd>
              </div>
            </div>

            {/* Info for developers */}
            <div className="w-full p-3 bg-gray-900/50 rounded-lg border border-gray-700">
              <p className="text-xs text-gray-400 font-mono">
                💡 <strong>Para desarrolladores:</strong> Los eventos de teclado se registran en la consola del
                navegador (F12) para facilitar la integración con el backend distribuido.
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center text-xs text-gray-500 font-mono">
          Frontend básico • Listo para integración distribuida
        </div>
      </div>
    </div>
  )
}
