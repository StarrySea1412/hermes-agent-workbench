import client from './client'

export function getUserBids(userId) {
  return client.get(`/users/${userId}/bids`)
}
