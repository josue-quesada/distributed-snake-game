"use client"

import { useEffect, useRef, useState } from "react"

// Tamaño de cada celda en píxeles
const CELL_SIZE = 20
// Número de filas y columnas
const GRID_SIZE = 20

// Tipos para las posiciones
type Position = {
  x: number
  y: number
}

// Tipos para las direcciones
type Direction = {
  x: number
  y: number
}

export default function SnakeGame() {
  // Referencia al canvas
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // Estado para la serpiente (inicialmente en el centro)
  const [snake, setSnake] = useState<Position[]>([{ x: 10, y: 10 }])

  // Estado para la dirección (inicialmente sin movimiento)
  const [direction, setDirection] = useState<Direction>({ x: 0, y: 0 })

  // Función para dibujar el tablero y la serpiente
  const drawGame = () => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext("2d")
    if (!ctx) return

    // Limpiar el canvas
    ctx.fillStyle = "#000"
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Dibujar la cuadrícula
    ctx.strokeStyle = "#222"
    for (let x = 0; x < GRID_SIZE; x++) {
      for (let y = 0; y < GRID_SIZE; y++) {
        ctx.strokeRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
      }
    }

    // Dibujar la serpiente
    ctx.fillStyle = "#0f0"
    snake.forEach((segment) => {
      ctx.fillRect(segment.x * CELL_SIZE, segment.y * CELL_SIZE, CELL_SIZE, CELL_SIZE)
    })
  }

  // Función para mover la serpiente
  const moveSnake = () => {
    setSnake((prevSnake) => {
      // Crear una copia de la serpiente
      const newSnake = [...prevSnake]

      // Calcular la nueva posición de la cabeza
      const head = { ...newSnake[0] }
      head.x += direction.x
      head.y += direction.y

      // Mantener la serpiente dentro de los límites
      head.x = (head.x + GRID_SIZE) % GRID_SIZE
      head.y = (head.y + GRID_SIZE) % GRID_SIZE

      // Añadir la nueva cabeza al principio
      newSnake.unshift(head)

      // Eliminar la cola (último segmento)
      newSnake.pop()

      return newSnake
    })
  }

  // Efecto para manejar las teclas de dirección
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Evitar que la serpiente vaya en dirección opuesta
      switch (e.key) {
        case "ArrowUp":
          if (direction.y !== 1) setDirection({ x: 0, y: -1 })
          break
        case "ArrowDown":
          if (direction.y !== -1) setDirection({ x: 0, y: 1 })
          break
        case "ArrowLeft":
          if (direction.x !== 1) setDirection({ x: -1, y: 0 })
          break
        case "ArrowRight":
          if (direction.x !== -1) setDirection({ x: 1, y: 0 })
          break
      }

      // Aquí se podría enviar la dirección al backend distribuido
      console.log("Tecla presionada:", e.key, "Nueva dirección:", { x: direction.x, y: direction.y })
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [direction])

  // Efecto para el bucle del juego
  useEffect(() => {
    // Dibujar el juego inicialmente
    drawGame()

    // Configurar el intervalo para mover la serpiente
    const gameInterval = setInterval(() => {
      moveSnake()
      drawGame()
    }, 150)

    // Limpiar el intervalo cuando el componente se desmonte
    return () => clearInterval(gameInterval)
  }, [snake, direction])

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={GRID_SIZE * CELL_SIZE}
        height={GRID_SIZE * CELL_SIZE}
        className="border-2 border-green-500 shadow-lg shadow-green-500/50"
      />
    </div>
  )
}
