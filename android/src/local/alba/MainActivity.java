package local.alba;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.graphics.Color;
import android.view.Gravity;
import android.widget.*;

/** Browser-backed app: uses the browser's secure login/session and opens providers outside embedded WebViews. */
public final class MainActivity extends Activity {
 private SharedPreferences preferences;
 @Override public void onCreate(Bundle state) {
  super.onCreate(state);preferences=getSharedPreferences("alba",MODE_PRIVATE);
  LinearLayout root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);root.setGravity(Gravity.CENTER);root.setPadding(36,40,36,40);root.setBackgroundColor(Color.rgb(245,243,232));
  ImageView icon=new ImageView(this);icon.setImageResource(R.drawable.albi);root.addView(icon,new LinearLayout.LayoutParams(180,180));
  TextView title=new TextView(this);title.setText("alba · albi");title.setTextColor(Color.rgb(43,73,56));title.setTextSize(36);title.setGravity(Gravity.CENTER);root.addView(title);
  TextView caption=new TextView(this);caption.setText("Uno spazio per parlare. Un quaderno per le idee.\nL’AI e i tuoi dati rimangono sul tuo server.");caption.setGravity(Gravity.CENTER);caption.setTextColor(Color.rgb(83,103,84));caption.setPadding(0,24,0,32);root.addView(caption);
  add(root,"Apri Alba",()->open("/"));add(root,"Tramonto · amministratore",()->open("/tramonto"));add(root,"Cambia server HTTPS",this::configure);
  TextView note=new TextView(this);note.setText("L’accesso viene conservato dal browser.\nQuesta app non contiene password, token o un modello AI.\nServe una connessione al server.");note.setTextSize(12);note.setGravity(Gravity.CENTER);note.setPadding(0,24,0,0);root.addView(note);setContentView(root);
 }
 private void add(LinearLayout root,String text,Runnable action){Button button=new Button(this);button.setText(text);button.setAllCaps(false);button.setOnClickListener(v->action.run());LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.setMargins(0,8,0,8);root.addView(button,lp);}
 private String base(){return preferences.getString("server",getString(R.string.default_server));}
 private void open(String path){try{Uri uri=Uri.parse(base()+path);if(!"https".equals(uri.getScheme())||uri.getHost()==null)throw new IllegalArgumentException();Intent intent=new Intent(Intent.ACTION_VIEW,uri);Bundle extras=new Bundle();extras.putBinder("android.support.customtabs.extra.SESSION",null);intent.putExtras(extras);intent.putExtra("android.support.customtabs.extra.TOOLBAR_COLOR",Color.rgb(225,235,218));startActivity(intent);}catch(Exception error){new AlertDialog.Builder(this).setMessage("Controlla l’indirizzo HTTPS e che sia installato un browser.").setPositiveButton("OK",null).show();}}
 private void configure(){EditText input=new EditText(this);input.setSingleLine();input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);input.setText(base());new AlertDialog.Builder(this).setTitle("Il tuo server Alba").setView(input).setNegativeButton("Annulla",null).setPositiveButton("Salva",(d,w)->{String value=input.getText().toString().trim().replaceAll("/+$","");Uri uri=Uri.parse(value);if("https".equals(uri.getScheme())&&uri.getHost()!=null&&uri.getUserInfo()==null&&uri.getQuery()==null&&uri.getFragment()==null&&(uri.getPath()==null||uri.getPath().isEmpty()))preferences.edit().putString("server",value).apply();else Toast.makeText(this,"Inserisci solo un’origine HTTPS, senza percorso o credenziali",Toast.LENGTH_LONG).show();}).show();}
}
