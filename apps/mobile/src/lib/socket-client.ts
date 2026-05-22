import { io, Socket } from 'socket.io-client'
import { getToken } from './token-store'

let socket: Socket | null = null

export function getSocket(): Socket | null {
  return socket
}

export function connectSocket(): Socket {
  if (socket?.connected) return socket

  const token = getToken()
  if (!token) throw new Error('No auth token')

  socket = io('/chat', {
    path: '/socket.io',
    auth: { token },
    transports: ['websocket', 'polling'],
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
  })

  return socket
}

export function disconnectSocket(): void {
  socket?.disconnect()
  socket = null
}

export function isSocketConnected(): boolean {
  return socket?.connected ?? false
}
