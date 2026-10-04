package local.alba;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/** The HTTP session is encrypted with a non-exportable Android Keystore key. */
final class SessionStore {
    private final Context context;
    private final String name;
    SessionStore(Context context){this(context,"native_session");}
    SessionStore(Context context,String name){this.context=context;this.name=name;}
    private SecretKey key() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        String alias="alba.native.session";
        if(!store.containsAlias(alias)){
            KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
            generator.generateKey();
        }
        return (SecretKey)store.getKey(alias,null);
    }
    synchronized void save(String value) throws Exception {
        if(value.isEmpty()){context.getSharedPreferences(name,0).edit().clear().commit();return;}
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
        String encrypted=Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(cipher.doFinal(value.getBytes("UTF-8")),Base64.NO_WRAP);
        context.getSharedPreferences(name,0).edit().putString("sealed",encrypted).commit();
    }
    synchronized String load(){
        try{
            String[] pair=context.getSharedPreferences(name,0).getString("sealed","").split(":");
            if(pair.length!=2)return "";
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(pair[0],0)));
            return new String(cipher.doFinal(Base64.decode(pair[1],0)),"UTF-8");
        }catch(Exception ignored){return "";}
    }
}
