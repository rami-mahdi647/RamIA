import axios from 'axios'
import { ENV } from './env'

export async function btcGetAddress(addr:string){
  const { data } = await axios.get(`${ENV.BTC_API}/address/${addr}`)
  return data
}
