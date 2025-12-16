"""
Script de téléchargement automatique des demos HLTV pour un tournoi
Usage: python download_demos.py --event-id 7902 --output bad/data/raw/blast_austin_2025
"""

import requests
from bs4 import BeautifulSoup
import re
import time
from pathlib import Path
import argparse
from datetime import datetime
from tqdm import tqdm


class HLTVDemoDownloader:
    """Télécharge automatiquement les demos d'un tournoi HLTV"""
    
    def __init__(self, event_id: int, output_dir: str):
        self.event_id = event_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = "https://www.hltv.org"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_match_list(self):
        """Récupère la liste des matchs du tournoi"""
        url = f"{self.base_url}/results?event={self.event_id}"
        
        print(f"Récupération de la liste des matchs depuis {url}...")
        response = self.session.get(url)
        
        if response.status_code != 200:
            print(f"Erreur lors de la récupération de la page: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Trouver tous les liens de matchs
        match_links = soup.find_all('a', class_='a-reset', href=re.compile(r'/matches/\d+/'))
        
        match_ids = []
        for link in match_links:
            match_id = re.search(r'/matches/(\d+)/', link['href'])
            if match_id:
                match_ids.append(match_id.group(1))
        
        # Dédupliquer (parfois les matchs apparaissent plusieurs fois)
        match_ids = list(dict.fromkeys(match_ids))
        
        print(f"✓ Trouvé {len(match_ids)} matchs")
        return match_ids
    
    def get_match_info(self, match_id: str):
        """Récupère les infos d'un match et le lien de la demo"""
        url = f"{self.base_url}/matches/{match_id}/"
        
        response = self.session.get(url)
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Récupérer les noms des équipes
        team_elements = soup.find_all('div', class_='teamName')
        if len(team_elements) < 2:
            return None
        
        team1 = team_elements[0].text.strip().lower().replace(' ', '-')
        team2 = team_elements[1].text.strip().lower().replace(' ', '-')
        
        # Récupérer la map
        map_element = soup.find('div', class_='mapname')
        if not map_element:
            return None
        map_name = map_element.text.strip().lower()
        
        # Récupérer la date
        date_element = soup.find('div', class_='date')
        if date_element:
            date_str = date_element.text.strip()
            try:
                # Parse format "23rd of June 2025"
                date_parts = re.search(r'(\d+)\w+ of (\w+) (\d{4})', date_str)
                if date_parts:
                    day = date_parts.group(1)
                    month_name = date_parts.group(2)
                    year = date_parts.group(3)
                    
                    month_map = {
                        'January': '01', 'February': '02', 'March': '03',
                        'April': '04', 'May': '05', 'June': '06',
                        'July': '07', 'August': '08', 'September': '09',
                        'October': '10', 'November': '11', 'December': '12'
                    }
                    month = month_map.get(month_name, '01')
                    date_formatted = f"{year}-{month}-{day.zfill(2)}"
                else:
                    date_formatted = datetime.now().strftime("%Y-%m-%d")
            except:
                date_formatted = datetime.now().strftime("%Y-%m-%d")
        else:
            date_formatted = datetime.now().strftime("%Y-%m-%d")
        
        # Chercher le lien de la demo (dans la section "GOTV Demo")
        demo_link = None
        demo_elements = soup.find_all('a', href=re.compile(r'.*\.dem\.bz2$|.*\.dem$'))
        
        if demo_elements:
            demo_link = demo_elements[0]['href']
            if not demo_link.startswith('http'):
                demo_link = self.base_url + demo_link
        
        if not demo_link:
            return None
        
        # Construire le nom du fichier
        filename = f"{date_formatted}-{team1}-vs-{team2}-{map_name}.dem"
        
        return {
            'match_id': match_id,
            'filename': filename,
            'demo_url': demo_link,
            'team1': team1,
            'team2': team2,
            'map': map_name,
            'date': date_formatted
        }
    
    def download_demo(self, match_info: dict):
        """Télécharge une demo"""
        output_path = self.output_dir / match_info['filename']
        
        # Vérifier si déjà téléchargé
        if output_path.exists():
            print(f"⊘ {match_info['filename']} déjà téléchargé")
            return True
        
        print(f"⬇ Téléchargement {match_info['filename']}...")
        
        try:
            response = self.session.get(match_info['demo_url'], stream=True)
            
            if response.status_code != 200:
                print(f"✗ Erreur {response.status_code} pour {match_info['filename']}")
                return False
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(output_path, 'wb') as f:
                with tqdm(total=total_size, unit='B', unit_scale=True, desc=match_info['filename']) as pbar:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
            
            # Si c'est un .bz2, décompresser
            if output_path.suffix == '.bz2':
                print("Décompression...")
                import bz2
                with bz2.open(output_path, 'rb') as f_in:
                    with open(output_path.with_suffix(''), 'wb') as f_out:
                        f_out.write(f_in.read())
                output_path.unlink()  # Supprimer le .bz2
            
            print(f"✓ {match_info['filename']} téléchargé")
            return True
            
        except Exception as e:
            print(f"✗ Erreur lors du téléchargement: {e}")
            if output_path.exists():
                output_path.unlink()
            return False
    
    def download_all(self, max_matches: int = None):
        """Télécharge toutes les demos du tournoi"""
        match_ids = self.get_match_list()
        
        if max_matches:
            match_ids = match_ids[:max_matches]
        
        print(f"\n{'='*60}")
        print(f"Téléchargement de {len(match_ids)} demos")
        print(f"{'='*60}\n")
        
        successful = 0
        failed = 0
        
        for i, match_id in enumerate(match_ids, 1):
            print(f"\n[{i}/{len(match_ids)}] Match ID: {match_id}")
            
            # Récupérer les infos du match
            match_info = self.get_match_info(match_id)
            
            if not match_info:
                print(f"✗ Impossible de récupérer les infos du match {match_id}")
                failed += 1
                continue
            
            if not match_info['demo_url']:
                print(f"✗ Pas de demo disponible pour {match_id}")
                failed += 1
                continue
            
            # Télécharger
            success = self.download_demo(match_info)
            
            if success:
                successful += 1
            else:
                failed += 1
            
            # Pause pour ne pas surcharger HLTV
            time.sleep(2)
        
        print(f"\n{'='*60}")
        print(f"Téléchargement terminé")
        print(f"✓ Succès: {successful}")
        print(f"✗ Échecs: {failed}")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description='Télécharge les demos HLTV d\'un tournoi')
    parser.add_argument('--event-id', type=int, required=True, help='ID du tournoi HLTV')
    parser.add_argument('--output', type=str, default='bad/data/raw', help='Dossier de sortie')
    parser.add_argument('--max', type=int, help='Nombre maximum de matchs à télécharger')
    
    args = parser.parse_args()
    
    downloader = HLTVDemoDownloader(args.event_id, args.output)
    downloader.download_all(max_matches=args.max)


if __name__ == "__main__":
    main()
